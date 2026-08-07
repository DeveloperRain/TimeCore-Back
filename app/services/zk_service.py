import platform
import socket
import subprocess
import threading
import time as time_module
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from zk import ZK

from app.config.logger import get_logger, log_exception
from app.exceptions import (
    DeviceAuthenticationError,
    DeviceClockDriftError,
    DeviceDisconnectedDuringSyncError,
    DeviceTimeoutError,
    DeviceUnavailableError,
)

IP_RELOJ = "192.168.1.50"
PORT = 4370
TIMEOUT = 30
FAST_FAIL_CONNECTION_TIMEOUT = 3
PASSWORD = 10
MAX_CLOCK_DRIFT_SECONDS = 300
SYNC_MONITOR_INTERVAL_SECONDS = 0.75
SYNC_MONITOR_FAILURE_LIMIT = 2
SYNC_MONITOR_PROBE_TIMEOUT_SECONDS = 1.0
DISCONNECT_HOLD_SECONDS = 4.0
DISCONNECT_RECOVERY_SUCCESS_LIMIT = 2
STATUS_CACHE_TTL_SECONDS = 10.0

logger = get_logger("services.zk")

ROLE_PRIVILEGES = {
    "usuario": 0,
    "admin": 14,
}

ATTENDANCE_STATUS = {
    0: "check_in",
    1: "check_out",
    2: "break_out",
    3: "break_in",
    4: "overtime_in",
    5: "overtime_out",
}


def role_to_privilege(role: str) -> int:
    """
    Convierte un rol de usuario en el privilegio numérico utilizado por el reloj.

    :param role: Rol que se debe convertir.
    :type role: str
    :return: Privilegio numérico correspondiente al rol.
    :rtype: int
    """
    return ROLE_PRIVILEGES.get(role, ROLE_PRIVILEGES["usuario"])


def privilege_to_role(privilege) -> str:
    """
    Convierte un privilegio numérico del reloj en un rol de la aplicación.

    :param privilege: Privilegio numérico que se debe interpretar.
    :type privilege: Any
    :return: Rol equivalente al privilegio recibido.
    :rtype: str
    """
    try:
        return "admin" if int(privilege) == ROLE_PRIVILEGES["admin"] else "usuario"
    except (TypeError, ValueError):
        return "usuario"


def normalize_user_id(user_id) -> str:
    """
    Normaliza el identificador de un usuario como texto sin espacios externos.

    :param user_id: Identificador del usuario.
    :type user_id: Any
    :return: Identificador normalizado.
    :rtype: str
    """
    return str(user_id).strip()


def normalize_attendance_status(status, punch=None) -> str:
    """
    Normaliza el tipo de marcación reportado por distintos modelos de reloj.

    :param status: Estado de asistencia reportado por el dispositivo.
    :type status: Any
    :param punch: Tipo alternativo de marcación reportado por el dispositivo.
    :type punch: Any or None
    :return: Estado de asistencia reconocido por la aplicación.
    :rtype: str
    """
    for value in (status, punch):
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            continue

        if numeric in ATTENDANCE_STATUS:
            return ATTENDANCE_STATUS[numeric]

    logger.warning(
        "Estado de asistencia no reconocido (status=%s, punch=%s). "
        "Se conservará como check_in para no perder la marcación.",
        status,
        punch,
    )
    return "check_in"


@dataclass
class _DisconnectLatch:
    """
    Mantiene el estado temporal de una desconexión detectada.

    Almacena el momento de la desconexión, los intentos de recuperación
    satisfactorios y una razón opcional asociada al evento.
    """
    disconnected_at: float = field(default_factory=time_module.monotonic)
    recovery_successes: int = 0
    reason: Optional[str] = None


@dataclass
class _SyncMonitorState:
    """
    Conserva el estado utilizado por el monitor de una sincronización.

    Incluye la conexión vigilada, los eventos de control, el estado de
    conectividad y los datos necesarios para detener o cancelar la operación.
    """
    key: str
    ip: str
    port: int
    conn: Any
    on_disconnect: Optional[Callable[[Dict[str, Any]], None]] = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    connected: bool = True
    reason: Optional[str] = None
    probe_mode: str = "ping"
    consecutive_failures: int = 0
    started_at: datetime = field(default_factory=datetime.utcnow)
    last_probe_at: Optional[datetime] = None
    thread: Optional[threading.Thread] = None


def call_if_available(conn, method_name: str, default: str = "Desconocido"):
    """
    Ejecuta un método de la conexión cuando está disponible y controla valores o errores.

    :param conn: Conexión activa o potencial con el dispositivo.
    :type conn: Any
    :param method_name: Nombre del método que se debe ejecutar.
    :type method_name: str
    :param default: Valor utilizado cuando el método no está disponible o falla.
    :type default: str
    :return: Valor devuelto por el método o el valor predeterminado.
    :rtype: Any
    """
    method = getattr(conn, method_name, None)

    if not callable(method):
        return default

    try:
        value = method()
        return default if value is None else value
    except Exception as e:
        logger.warning("No se pudo obtener %s del reloj: %s", method_name, e)
        return default


class ZKService:
    """
    Proporciona operaciones de comunicación y sincronización con relojes ZKTeco.

    Gestiona conexiones, usuarios, asistencias, estado del dispositivo,
    sincronización de hora y detección de desconexiones durante operaciones.
    """
    _device_locks: Dict[str, threading.RLock] = {}
    _device_locks_guard = threading.Lock()
    _sync_states: Dict[str, _SyncMonitorState] = {}
    _sync_states_guard = threading.Lock()
    _disconnect_latches: Dict[str, _DisconnectLatch] = {}
    _status_cache: Dict[str, tuple[bool, float]] = {}
    _status_guard = threading.RLock()

    @staticmethod
    def _device_key(ip: str = None, port: int = None) -> str:
        """
        Construye la clave interna utilizada para identificar un dispositivo.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :return: Clave compuesta por dirección IP y puerto.
        :rtype: str
        """
        return f"{ip or IP_RELOJ}:{int(port or PORT)}"

    @staticmethod
    def _get_device_lock(ip: str = None, port: int = None) -> threading.RLock:
        """
        Obtiene o crea el bloqueo reentrante asociado a un dispositivo.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :return: Bloqueo asociado al dispositivo.
        :rtype: threading.RLock
        """
        key = ZKService._device_key(ip, port)
        with ZKService._device_locks_guard:
            lock = ZKService._device_locks.get(key)
            if lock is None:
                lock = threading.RLock()
                ZKService._device_locks[key] = lock
            return lock

    @staticmethod
    @contextmanager
    def _locked_device(ip: str = None, port: int = None):
        """
        Controla el acceso exclusivo a las operaciones de un dispositivo.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str or None
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int or None
        :return: Contexto que mantiene bloqueado el dispositivo durante la operación.
        :rtype: Iterator[None]
        """
        lock = ZKService._get_device_lock(ip, port)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    @staticmethod
    def mark_device_disconnected(
        ip: str = None,
        port: int = None,
        reason: Optional[str] = None,
    ) -> None:
        """
        Registra un estado de desconexión estable para un dispositivo.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :param reason: Razón opcional asociada a la desconexión.
        :type reason: str or None
        :return: No devuelve ningún valor.
        :rtype: None
        """
        key = ZKService._device_key(ip, port)
        now = time_module.monotonic()
        with ZKService._status_guard:
            ZKService._disconnect_latches[key] = _DisconnectLatch(
                disconnected_at=now,
                recovery_successes=0,
                reason=reason,
            )
            ZKService._status_cache[key] = (False, now)

    @staticmethod
    def mark_device_connected(ip: str = None, port: int = None) -> None:
        """
        Registra una conexión confirmada mediante una operación real completada.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :return: No devuelve ningún valor.
        :rtype: None
        """
        key = ZKService._device_key(ip, port)
        now = time_module.monotonic()
        with ZKService._status_guard:
            ZKService._disconnect_latches.pop(key, None)
            ZKService._status_cache[key] = (True, now)

    @staticmethod
    def is_disconnect_latched(ip: str = None, port: int = None) -> bool:
        """
        Comprueba si un dispositivo conserva un estado de desconexión fijado.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :return: Indica si existe un estado de desconexión fijado.
        :rtype: bool
        """
        key = ZKService._device_key(ip, port)
        with ZKService._status_guard:
            return key in ZKService._disconnect_latches

    @staticmethod
    def _get_cached_status(ip: str = None, port: int = None) -> Optional[bool]:
        """
        Obtiene el estado de conexión almacenado en caché cuando sigue vigente.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :return: Estado almacenado o ``None`` si no existe o expiró.
        :rtype: bool or None
        """
        key = ZKService._device_key(ip, port)
        now = time_module.monotonic()
        with ZKService._status_guard:
            cached = ZKService._status_cache.get(key)
            if cached is None:
                return None
            value, checked_at = cached
            if now - checked_at > STATUS_CACHE_TTL_SECONDS:
                return None
            return bool(value)

    @staticmethod
    def _get_sync_state(ip: str = None, port: int = None) -> Optional[_SyncMonitorState]:
        """
        Obtiene el estado interno del monitor de sincronización de un dispositivo.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :return: Estado interno de sincronización o ``None``.
        :rtype: _SyncMonitorState or None
        """
        key = ZKService._device_key(ip, port)
        with ZKService._sync_states_guard:
            return ZKService._sync_states.get(key)

    @staticmethod
    def get_sync_state(ip: str = None, port: int = None) -> Optional[Dict[str, Any]]:
        """
        Obtiene una representación serializable del estado de sincronización.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :return: Datos del monitor de sincronización o ``None`` si no hay una operación activa.
        :rtype: dict[str, Any] or None
        """
        state = ZKService._get_sync_state(ip, port)
        if state is None:
            return None

        return {
            "active": not state.stop_event.is_set(),
            "connected": bool(state.connected and not state.cancel_event.is_set()),
            "cancelled": state.cancel_event.is_set(),
            "reason": state.reason,
            "probe_mode": state.probe_mode,
            "started_at": state.started_at.isoformat(),
            "last_probe_at": state.last_probe_at.isoformat()
            if state.last_probe_at
            else None,
        }

    @staticmethod
    def _ping_device(ip: str, timeout: float = SYNC_MONITOR_PROBE_TIMEOUT_SECONDS) -> bool:
        """
        Comprueba la disponibilidad de un dispositivo mediante una solicitud de ping.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param timeout: Tiempo máximo de espera expresado en segundos.
        :type timeout: float
        :return: Indica si el dispositivo respondió al sondeo.
        :rtype: bool
        """
        system = platform.system().lower()
        timeout = max(0.25, float(timeout))

        if system == "windows":
            command = ["ping", "-n", "1", "-w", str(max(250, int(timeout * 1000))), ip]
        else:
            command = ["ping", "-c", "1", "-W", str(max(1, int(round(timeout)))), ip]

        try:
            result = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout + 1.0,
                check=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    @staticmethod
    def _tcp_probe(ip: str, port: int, timeout: float = SYNC_MONITOR_PROBE_TIMEOUT_SECONDS) -> bool:
        """
        Comprueba la disponibilidad de un puerto mediante una conexión TCP breve.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :param timeout: Tiempo máximo de espera expresado en segundos.
        :type timeout: float
        :return: Indica si la conexión TCP pudo establecerse.
        :rtype: bool
        """
        try:
            with socket.create_connection((ip, int(port or PORT)), timeout=max(0.25, timeout)):
                return True
        except OSError:
            return False

    @staticmethod
    def _force_close_connection(conn) -> None:
        """
        Cierra de forma forzada el socket interno de una conexión PyZK.

        :param conn: Conexión activa o potencial con el dispositivo.
        :type conn: Any
        :return: No devuelve ningún valor.
        :rtype: None
        """
        if conn is None:
            return

        sock = getattr(conn, "_ZK__sock", None)
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

        try:
            conn.is_connect = False
        except Exception:
            pass

    @staticmethod
    def _configure_socket_keepalive(conn) -> None:
        """
        Configura opciones de mantenimiento de conexión en el socket TCP de PyZK.

        :param conn: Conexión activa o potencial con el dispositivo.
        :type conn: Any
        :return: No devuelve ningún valor.
        :rtype: None
        """
        sock = getattr(conn, "_ZK__sock", None)
        if sock is None or not bool(getattr(conn, "tcp", False)):
            return

        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            if platform.system().lower() == "windows" and hasattr(socket, "SIO_KEEPALIVE_VALS"):
                sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 1000, 1000))
            else:
                if hasattr(socket, "TCP_KEEPIDLE"):
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 2)
                if hasattr(socket, "TCP_KEEPINTVL"):
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 1)
                if hasattr(socket, "TCP_KEEPCNT"):
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 2)
        except OSError as exc:
            logger.debug("No se pudo configurar keepalive para %s: %s", conn, exc)

    @staticmethod
    def _start_sync_monitor(
        ip: str,
        port: int,
        conn,
        on_disconnect: Optional[Callable[[Dict[str, Any]], None]] = None,
        fail_fast: bool = False,
    ) -> _SyncMonitorState:
        """
        Inicia un monitor independiente para detectar desconexiones durante una sincronización.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :param conn: Conexión activa o potencial con el dispositivo.
        :type conn: Any
        :param on_disconnect: Función opcional invocada cuando se detecta una desconexión.
        :type on_disconnect: Callable[[Dict[str, Any]], None] or None
        :param fail_fast: Indica si deben omitirse intentos adicionales de conexión.
        :type fail_fast: bool
        :return: Estado del monitor de sincronización iniciado.
        :rtype: _SyncMonitorState
        """
        key = ZKService._device_key(ip, port)
        ping_available = ZKService._ping_device(ip)
        tcp_probe_available = (
            False
            if ping_available
            else ZKService._tcp_probe(ip, int(port or PORT))
        )
        probe_mode = (
            "ping"
            if ping_available
            else "tcp"
            if tcp_probe_available
            else "keepalive"
        )
        state = _SyncMonitorState(
            key=key,
            ip=ip,
            port=int(port or PORT),
            conn=conn,
            on_disconnect=on_disconnect,
            probe_mode=probe_mode,
        )

        with ZKService._sync_states_guard:
            ZKService._sync_states[key] = state

        def monitor() -> None:
            """
            Vigila periódicamente la conectividad del dispositivo durante una sincronización.

            :return: No devuelve ningún valor.
            :rtype: None
            """
            while not state.stop_event.wait(SYNC_MONITOR_INTERVAL_SECONDS):
                if state.probe_mode == "ping":
                    reachable = ZKService._ping_device(
                        state.ip,
                        SYNC_MONITOR_PROBE_TIMEOUT_SECONDS,
                    )
                elif state.probe_mode == "tcp":
                    reachable = ZKService._tcp_probe(
                        state.ip,
                        state.port,
                        SYNC_MONITOR_PROBE_TIMEOUT_SECONDS,
                    )
                else:
                    # Si el dispositivo no admite ping ni una segunda conexión
                    # TCP, el socket principal queda protegido por keepalive y
                    # cualquier error de lectura se convierte en desconexión.
                    continue

                state.last_probe_at = datetime.utcnow()

                if reachable:
                    state.connected = True
                    state.consecutive_failures = 0
                    continue

                state.consecutive_failures += 1
                failure_limit = 1 if fail_fast else SYNC_MONITOR_FAILURE_LIMIT
                if state.consecutive_failures < failure_limit:
                    continue

                state.connected = False
                state.reason = "Se perdió la comunicación de red con el reloj durante la sincronización"
                state.cancel_event.set()
                ZKService.mark_device_disconnected(
                    state.ip,
                    state.port,
                    reason=state.reason,
                )

                details = {
                    "ip": state.ip,
                    "port": state.port,
                    "stage": "network_watchdog",
                    "probe_mode": state.probe_mode,
                    "detected_at": datetime.utcnow().isoformat(),
                }

                # Primero se corta el socket para desbloquear PyZK de inmediato;
                # la actualización de BD se realiza después y no retrasa la cancelación.
                ZKService._force_close_connection(state.conn)

                if state.on_disconnect is not None:
                    try:
                        state.on_disconnect(details)
                    except Exception as exc:
                        logger.warning(
                            "No se pudo notificar la desconexión de %s:%s: %s",
                            state.ip,
                            state.port,
                            exc,
                        )

                logger.error(
                    "Se canceló la sincronización de %s:%s porque el reloj fue desconectado",
                    state.ip,
                    state.port,
                )
                return

        state.thread = threading.Thread(
            target=monitor,
            name=f"timecore-watchdog-{ip}-{port}",
            daemon=True,
        )
        state.thread.start()
        return state

    @staticmethod
    def _stop_sync_monitor(state: Optional[_SyncMonitorState]) -> None:
        """
        Detiene un monitor de sincronización y elimina su estado interno.

        :param state: Estado opcional del monitor de sincronización.
        :type state: _SyncMonitorState or None
        :return: No devuelve ningún valor.
        :rtype: None
        """
        if state is None:
            return

        state.stop_event.set()
        if state.thread and state.thread.is_alive() and state.thread is not threading.current_thread():
            state.thread.join(timeout=2.0)

        with ZKService._sync_states_guard:
            if ZKService._sync_states.get(state.key) is state:
                ZKService._sync_states.pop(state.key, None)

    @staticmethod
    def _raise_if_sync_cancelled(
        state: Optional[_SyncMonitorState],
        stage: str,
    ) -> None:
        """
        Interrumpe la operación cuando el monitor marcó la sincronización como cancelada.

        :param state: Estado opcional del monitor de sincronización.
        :type state: _SyncMonitorState or None
        :param stage: Etapa de la operación en la que se comprueba la cancelación.
        :type stage: str
        :return: No devuelve ningún valor.
        :rtype: None
        :raises DeviceDisconnectedDuringSyncError: Si la sincronización fue cancelada por una desconexión.
        """
        if state is None or not state.cancel_event.is_set():
            return

        raise DeviceDisconnectedDuringSyncError(
            details={
                "ip": state.ip,
                "port": state.port,
                "stage": stage,
                "reason": state.reason,
                "probe_mode": state.probe_mode,
            }
        )

    @staticmethod
    def check_device_status(ip: str, port: int = PORT, timeout: int = 2) -> bool:
        """
        Comprueba el estado de conexión de un dispositivo respetando monitores, bloqueos y caché.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :param timeout: Tiempo máximo de espera expresado en segundos.
        :type timeout: int
        :return: Indica si el dispositivo se considera conectado.
        :rtype: bool
        """
        target_port = int(port or PORT)
        key = ZKService._device_key(ip, target_port)

        # Si hay una sincronización vigilada, su watchdog es la fuente de verdad.
        sync_state = ZKService._get_sync_state(ip, target_port)
        if sync_state is not None:
            connected = bool(
                sync_state.connected
                and not sync_state.cancel_event.is_set()
            )
            if not connected:
                ZKService.mark_device_disconnected(
                    ip,
                    target_port,
                    reason=sync_state.reason,
                )
            else:
                with ZKService._status_guard:
                    ZKService._status_cache[key] = (
                        True,
                        time_module.monotonic(),
                    )
            return connected

        now = time_module.monotonic()
        with ZKService._status_guard:
            latch = ZKService._disconnect_latches.get(key)
            if latch is not None and now - latch.disconnected_at < DISCONNECT_HOLD_SECONDS:
                ZKService._status_cache[key] = (False, now)
                return False

        lock = ZKService._get_device_lock(ip, target_port)
        if not lock.acquire(blocking=False):
            # Nunca asumir conectado solamente porque otra operación tiene el
            # candado. Se conserva el último resultado estable; tras una
            # desconexión el latch siempre domina y devuelve False.
            cached = ZKService._get_cached_status(ip, target_port)
            return bool(cached) if cached is not None else False

        try:
            try:
                with socket.create_connection(
                    (ip, target_port),
                    timeout=max(1, int(timeout)),
                ):
                    reachable = True
            except Exception as exc:
                logger.warning(
                    "Reloj %s:%s sin conexion: %s",
                    ip,
                    target_port,
                    exc,
                )
                reachable = False
        finally:
            lock.release()

        now = time_module.monotonic()
        with ZKService._status_guard:
            latch = ZKService._disconnect_latches.get(key)

            if not reachable:
                if latch is None:
                    latch = _DisconnectLatch(
                        disconnected_at=now,
                        reason="El sondeo de conectividad no respondió",
                    )
                    ZKService._disconnect_latches[key] = latch
                else:
                    latch.recovery_successes = 0
                ZKService._status_cache[key] = (False, now)
                return False

            if latch is not None:
                latch.recovery_successes += 1
                if latch.recovery_successes < DISCONNECT_RECOVERY_SUCCESS_LIMIT:
                    # Un único éxito puede ser un resultado transitorio del
                    # sistema operativo. Se requieren dos confirmaciones.
                    ZKService._status_cache[key] = (False, now)
                    return False
                ZKService._disconnect_latches.pop(key, None)

            ZKService._status_cache[key] = (True, now)
            return True

    @staticmethod
    def _create_connection(
        ip: str = None,
        port: int = None,
        password: str = None,
        fail_fast: bool = False,
    ):
        """
        Crea una conexión con el reloj utilizando los modos de comunicación disponibles.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :param password: Contraseña opcional de comunicación del dispositivo.
        :type password: str
        :param fail_fast: Indica si deben omitirse intentos adicionales de conexión.
        :type fail_fast: bool
        :return: Conexión activa con el dispositivo.
        :rtype: Any
        :raises DeviceAuthenticationError: Si el dispositivo rechaza la contraseña.
        :raises DeviceTimeoutError: Si se agota el tiempo de conexión.
        :raises DeviceUnavailableError: Si no es posible comunicarse con el dispositivo.
        """
        target_ip = ip or IP_RELOJ
        target_port = int(port or PORT)

        try:
            target_password = int(password if password not in (None, "") else PASSWORD)
        except (TypeError, ValueError):
            target_password = 0

        # En sincronización masiva se usa fail_fast=True: sólo se hace el
        # intento principal TCP. Si falla o el reloj ya está marcado como
        # desconectado, no se prueban variantes TCP/UDP y el flujo continúa
        # inmediatamente con el siguiente reloj.
        if fail_fast and ZKService.is_disconnect_latched(target_ip, target_port):
            raise DeviceUnavailableError(
                "El reloj está marcado como desconectado; se omitieron los reintentos de conexión"
            )

        attempts = [
            {"force_udp": False, "ommit_ping": False, "label": "TCP"},
        ]

        if not fail_fast:
            attempts.extend(
                [
                    {"force_udp": False, "ommit_ping": True, "label": "TCP sin ping"},
                    {"force_udp": True, "ommit_ping": False, "label": "UDP"},
                    {"force_udp": True, "ommit_ping": True, "label": "UDP sin ping"},
                ]
            )

        last_error = None

        for attempt in attempts:
            try:
                logger.info(
                    "Conectando al reloj %s:%s por %s",
                    target_ip,
                    target_port,
                    attempt["label"],
                )

                zk = ZK(
                    target_ip,
                    port=target_port,
                    timeout=(FAST_FAIL_CONNECTION_TIMEOUT if fail_fast else TIMEOUT),
                    password=target_password,
                    force_udp=attempt["force_udp"],
                    ommit_ping=attempt["ommit_ping"],
                )

                conn = zk.connect()
                ZKService._configure_socket_keepalive(conn)
                logger.info("Conexion establecida con el reloj por %s", attempt["label"])
                return conn

            except socket.timeout as e:
                last_error = e
                logger.warning("Tiempo agotado conectando al reloj por %s", attempt["label"])

            except ConnectionRefusedError as e:
                last_error = e
                logger.warning("El reloj rechazo la conexion por %s", attempt["label"])

            except Exception as e:
                last_error = e
                logger.warning("No se pudo conectar al reloj por %s: %s", attempt["label"], e)

        error_text = str(last_error or "").lower()

        if "unauthorized" in error_text or "password" in error_text:
            log_exception(logger, last_error, "El reloj rechazó la contraseña de comunicación")
            raise DeviceAuthenticationError()

        if isinstance(last_error, socket.timeout) or "timed out" in error_text:
            log_exception(logger, last_error, "Tiempo agotado conectando al reloj")
            raise DeviceTimeoutError()

        if isinstance(last_error, ConnectionRefusedError):
            log_exception(logger, last_error, "El reloj rechazó la conexión")
            raise DeviceUnavailableError("El reloj rechazó la conexión")

        log_exception(logger, last_error, "Error de conexión con el reloj")
        raise DeviceUnavailableError("No fue posible comunicarse con el reloj")

    @staticmethod
    def _disconnect(conn):
        """
        Cierra una conexión activa con el dispositivo.

        :param conn: Conexión activa o potencial con el dispositivo.
        :type conn: Any
        :return: No devuelve ningún valor.
        :rtype: None
        """
        try:
            conn.disconnect()
        except Exception as e:
            logger.warning("No se pudo cerrar la conexion con el reloj: %s", e)

    @staticmethod
    def _build_clock_status(
        device_time,
        server_time: datetime = None,
        max_drift_seconds: int = MAX_CLOCK_DRIFT_SECONDS,
    ) -> Dict[str, Any]:
        """
        Compara la hora del dispositivo con la hora del servidor y calcula el desfase.

        :param device_time: Fecha y hora reportadas por el dispositivo.
        :type device_time: Any
        :param server_time: Fecha y hora opcionales del servidor utilizadas para la comparación.
        :type server_time: datetime
        :param max_drift_seconds: Desfase máximo permitido expresado en segundos.
        :type max_drift_seconds: int
        :return: Resumen del estado de sincronización de fecha y hora.
        :rtype: dict[str, Any]
        :raises DeviceUnavailableError: Si el dispositivo no devuelve una fecha y hora válidas.
        """
        if not isinstance(device_time, datetime):
            raise DeviceUnavailableError(
                "El reloj no devolvió una fecha y hora válidas"
            )

        current_server_time = server_time or datetime.now()

        # PyZK normalmente devuelve datetimes sin zona horaria. Se compara contra
        # la hora local del servidor que ejecuta TimeCore.
        if device_time.tzinfo is not None and current_server_time.tzinfo is None:
            device_time = device_time.replace(tzinfo=None)
        elif device_time.tzinfo is None and current_server_time.tzinfo is not None:
            current_server_time = current_server_time.replace(tzinfo=None)

        drift_seconds = int((device_time - current_server_time).total_seconds())
        absolute_drift_seconds = abs(drift_seconds)
        threshold = max(1, int(max_drift_seconds))

        return {
            "device_time": device_time.isoformat(),
            "server_time": current_server_time.isoformat(),
            "drift_seconds": drift_seconds,
            "absolute_drift_seconds": absolute_drift_seconds,
            "drift_minutes": round(drift_seconds / 60, 2),
            "in_sync": absolute_drift_seconds <= threshold,
            "max_drift_seconds": threshold,
        }

    @staticmethod
    def get_device_time_status(
        ip: str = None,
        port: int = None,
        password: str = None,
        max_drift_seconds: int = MAX_CLOCK_DRIFT_SECONDS,
    ) -> Dict[str, Any]:
        """
        Obtiene la hora del dispositivo y la compara con la hora del servidor.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :param password: Contraseña opcional de comunicación del dispositivo.
        :type password: str
        :param max_drift_seconds: Desfase máximo permitido expresado en segundos.
        :type max_drift_seconds: int
        :return: Resumen del estado de sincronización de fecha y hora.
        :rtype: dict[str, Any]
        """
        conn = None

        with ZKService._locked_device(ip, port):
            try:
                conn = ZKService._create_connection(ip, port, password)
                device_time = conn.get_time()

                return ZKService._build_clock_status(
                    device_time=device_time,
                    server_time=datetime.now(),
                    max_drift_seconds=max_drift_seconds,
                )
            finally:
                if conn:
                    ZKService._disconnect(conn)

    @staticmethod
    def sync_device_time(
        ip: str = None,
        port: int = None,
        password: str = None,
        max_drift_seconds: int = MAX_CLOCK_DRIFT_SECONDS,
    ) -> Dict[str, Any]:
        """
        Ajusta la hora del dispositivo y verifica el resultado mediante una conexión nueva.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :param password: Contraseña opcional de comunicación del dispositivo.
        :type password: str
        :param max_drift_seconds: Desfase máximo permitido expresado en segundos.
        :type max_drift_seconds: int
        :return: Estado verificado de la fecha y hora después del ajuste.
        :rtype: dict[str, Any]
        :raises DeviceClockDriftError: Si el dispositivo continúa desfasado después de los intentos de ajuste.
        """
        target_ip = ip or IP_RELOJ
        target_port = int(port or PORT)
        last_status: Dict[str, Any] | None = None

        with ZKService._locked_device(ip, port):
            for attempt_number in range(1, 3):
                conn = None
                disabled = False
                target_time = datetime.now().replace(microsecond=0)

                try:
                    conn = ZKService._create_connection(ip, port, password)

                    try:
                        conn.disable_device()
                        disabled = True
                    except Exception as e:
                        logger.warning(
                            "No se pudo bloquear temporalmente el reloj antes de ajustar la hora: %s",
                            e,
                        )

                    set_result = conn.set_time(target_time)

                    if set_result is False:
                        logger.warning(
                            "El reloj %s:%s respondió False al intentar ajustar la hora",
                            target_ip,
                            target_port,
                        )

                    try:
                        conn.refresh_data()
                    except Exception as e:
                        logger.warning(
                            "No se pudo refrescar el reloj después de ajustar la hora: %s",
                            e,
                        )
                finally:
                    if conn:
                        if disabled:
                            try:
                                conn.enable_device()
                            except Exception as e:
                                logger.warning(
                                    "No se pudo reactivar el reloj después de ajustar la hora: %s",
                                    e,
                                )
                        ZKService._disconnect(conn)

                # Da tiempo al dispositivo para persistir el cambio y verifica
                # desde una sesión nueva, evitando lecturas almacenadas en caché.
                time_module.sleep(1.0)

                verify_conn = None
                try:
                    verify_conn = ZKService._create_connection(ip, port, password)
                    verified_time = verify_conn.get_time()
                    server_time = datetime.now().replace(microsecond=0)

                    last_status = ZKService._build_clock_status(
                        device_time=verified_time,
                        server_time=server_time,
                        max_drift_seconds=max_drift_seconds,
                    )
                    last_status.update(
                        {
                            "adjusted_to": target_time.isoformat(),
                            "attempt": attempt_number,
                            "verified_after_reconnect": True,
                        }
                    )
                finally:
                    if verify_conn:
                        ZKService._disconnect(verify_conn)

                if last_status["in_sync"]:
                    logger.info(
                        "Hora ajustada y verificada en reloj %s:%s. "
                        "Reloj=%s, servidor=%s, desfase=%ss, intento=%s",
                        target_ip,
                        target_port,
                        last_status["device_time"],
                        last_status["server_time"],
                        last_status["drift_seconds"],
                        attempt_number,
                    )
                    return last_status

                logger.warning(
                    "El reloj %s:%s siguió desfasado después del intento %s: %ss",
                    target_ip,
                    target_port,
                    attempt_number,
                    last_status["drift_seconds"],
                )

            raise DeviceClockDriftError(
                message=(
                    "El reloj recibió la orden de ajuste, pero conservó una fecha "
                    "y hora incorrectas. Revisa la configuración de fecha del "
                    "dispositivo o ajústala directamente desde su menú."
                ),
                details={
                    **(last_status or {}),
                    "ip": target_ip,
                    "port": target_port,
                    "attempts": 2,
                },
            )

    @staticmethod
    def get_device_info(ip: str = None, port: int = None, password: str = None) -> Dict[str, Any]:
        """
        Obtiene información general y de red disponible del dispositivo.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :param password: Contraseña opcional de comunicación del dispositivo.
        :type password: str
        :return: Datos generales del dispositivo.
        :rtype: dict[str, Any]
        """
        conn = None
        target_ip = ip or IP_RELOJ

        try:
            conn = ZKService._create_connection(ip, port, password)

            return {
                "name": str(call_if_available(conn, "get_device_name")),
                "serial": str(call_if_available(conn, "get_serialnumber")),
                "firmware": str(call_if_available(conn, "get_firmware_version")),
                "mac_address": str(call_if_available(conn, "get_mac")),
                "device_time": str(call_if_available(conn, "get_time")),
                "network_params": {
                    "ip": target_ip,
                    "gateway": "Desconocido",
                    "dns": "Desconocido",
                },
            }

        except Exception as e:
            log_exception(logger, e, "Error al obtener informacion del reloj")
            raise

        finally:
            if conn:
                ZKService._disconnect(conn)

    @staticmethod
    def get_all_users(ip: str = None, port: int = None, password: str = None) -> List[Dict[str, Any]]:
        """
        Obtiene y normaliza todos los usuarios registrados en el dispositivo.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :param password: Contraseña opcional de comunicación del dispositivo.
        :type password: str
        :return: Lista de usuarios obtenidos del reloj.
        :rtype: list[dict[str, Any]]
        """
        conn = None

        with ZKService._locked_device(ip, port):
            try:
                conn = ZKService._create_connection(ip, port, password)
                usuarios = conn.get_users() or []

                return [
                    {
                        "uid": int(u.uid),
                        "user_id": normalize_user_id(u.user_id),
                        "name": str(u.name or "").strip() or f"Usuario {u.uid}",
                        "role": privilege_to_role(getattr(u, "privilege", 0)),
                    }
                    for u in usuarios
                ]
            finally:
                if conn:
                    ZKService._disconnect(conn)

    @staticmethod
    def get_sync_snapshot(
        ip: str = None,
        port: int = None,
        password: str = None,
        on_disconnect: Optional[Callable[[Dict[str, Any]], None]] = None,
        fail_fast: bool = False,
    ) -> Dict[str, Any]:
        """
        Lee usuarios, asistencias y estado de hora mediante una única sesión vigilada.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :param password: Contraseña opcional de comunicación del dispositivo.
        :type password: str
        :param on_disconnect: Función opcional invocada cuando se detecta una desconexión.
        :type on_disconnect: Callable[[Dict[str, Any]], None] or None
        :param fail_fast: Indica si deben omitirse intentos adicionales de conexión.
        :type fail_fast: bool
        :return: Datos de usuarios, asistencias y estado de hora del dispositivo.
        :rtype: dict[str, Any]
        :raises DeviceClockDriftError: Si la fecha y hora del dispositivo están fuera del límite permitido.
        :raises DeviceDisconnectedDuringSyncError: Si se pierde la conexión durante la lectura.
        """
        conn = None
        monitor_state: Optional[_SyncMonitorState] = None
        target_ip = ip or IP_RELOJ
        target_port = int(port or PORT)

        with ZKService._locked_device(ip, port):
            try:
                conn = ZKService._create_connection(
                    ip,
                    port,
                    password,
                    fail_fast=fail_fast,
                )
                monitor_state = ZKService._start_sync_monitor(
                    target_ip,
                    target_port,
                    conn,
                    on_disconnect=on_disconnect,
                    fail_fast=fail_fast,
                )

                ZKService._raise_if_sync_cancelled(monitor_state, "connected")
                device_time = conn.get_time()
                ZKService._raise_if_sync_cancelled(monitor_state, "clock_read")

                clock_status = ZKService._build_clock_status(
                    device_time=device_time,
                    server_time=datetime.now(),
                    max_drift_seconds=MAX_CLOCK_DRIFT_SECONDS,
                )

                if not clock_status["in_sync"]:
                    ZKService.mark_device_connected(target_ip, target_port)
                    raise DeviceClockDriftError(
                        details={
                            **clock_status,
                            "ip": target_ip,
                            "port": target_port,
                        }
                    )

                # Esta operación solo lee información. No se deshabilita el
                # dispositivo porque, si se pierde la red, podría quedar
                # bloqueado sin poder ejecutar enable_device().
                attendance_objects = conn.get_attendance() or []
                ZKService._raise_if_sync_cancelled(monitor_state, "attendance_read")

                user_objects = conn.get_users() or []
                ZKService._raise_if_sync_cancelled(monitor_state, "users_read")

                users = [
                    {
                        "uid": int(u.uid),
                        "user_id": normalize_user_id(u.user_id),
                        "name": str(u.name or "").strip() or f"Usuario {u.uid}",
                        "role": privilege_to_role(getattr(u, "privilege", 0)),
                    }
                    for u in user_objects
                ]

                users_by_id = {user["user_id"]: user for user in users}
                users_by_uid = {int(user["uid"]): user for user in users}
                attendance: List[Dict[str, Any]] = []

                for item in attendance_objects:
                    ZKService._raise_if_sync_cancelled(monitor_state, "attendance_processing")
                    user_id = normalize_user_id(getattr(item, "user_id", ""))
                    raw_uid = getattr(item, "uid", None)
                    uid = None

                    try:
                        uid = int(raw_uid) if raw_uid not in (None, "") else None
                    except (TypeError, ValueError):
                        uid = None

                    linked_user = users_by_id.get(user_id)
                    if linked_user is None and uid is not None:
                        linked_user = users_by_uid.get(uid)

                    if linked_user is not None:
                        uid = int(linked_user["uid"])
                        user_id = linked_user["user_id"]
                        name = linked_user["name"]
                    else:
                        name = f"Usuario {user_id or uid or 'desconocido'}"

                    timestamp = getattr(item, "timestamp", None)
                    if timestamp is None:
                        logger.warning("Marcación sin timestamp descartada: %r", item)
                        continue

                    attendance.append(
                        {
                            "uid": uid,
                            "user_id": user_id or str(uid or ""),
                            "name": name,
                            "timestamp": timestamp,
                            "status": normalize_attendance_status(
                                getattr(item, "status", None),
                                getattr(item, "punch", None),
                            ),
                        }
                    )

                ZKService._raise_if_sync_cancelled(monitor_state, "snapshot_complete")
                latest = sorted(
                    attendance,
                    key=lambda value: value.get("timestamp"),
                )[-5:]
                logger.info(
                    "Lectura del reloj %s:%s: %s usuarios, %s asistencias. Últimas: %s",
                    target_ip,
                    target_port,
                    len(users),
                    len(attendance),
                    latest,
                )

                ZKService.mark_device_connected(target_ip, target_port)
                return {
                    "users": users,
                    "attendance": attendance,
                    "clock": clock_status,
                }

            except DeviceDisconnectedDuringSyncError:
                raise
            except Exception as e:
                error_text = str(e).lower()
                looks_like_network_loss = isinstance(
                    e,
                    (OSError, socket.timeout, ConnectionError),
                ) or any(
                    token in error_text
                    for token in (
                        "timed out",
                        "timeout",
                        "socket",
                        "connection",
                        "network",
                        "unreachable",
                        "closed",
                        "reset",
                        "broken pipe",
                    )
                )

                if monitor_state is not None and (
                    monitor_state.cancel_event.is_set() or looks_like_network_loss
                ):
                    if not monitor_state.cancel_event.is_set():
                        monitor_state.connected = False
                        monitor_state.reason = (
                            "Se perdió la comunicación con el reloj durante la sincronización"
                        )
                        monitor_state.cancel_event.set()
                        ZKService.mark_device_disconnected(
                            target_ip,
                            target_port,
                            reason=monitor_state.reason,
                        )
                        ZKService._force_close_connection(monitor_state.conn)
                        if monitor_state.on_disconnect is not None:
                            try:
                                monitor_state.on_disconnect(
                                    {
                                        "ip": target_ip,
                                        "port": target_port,
                                        "stage": "device_read",
                                        "probe_mode": monitor_state.probe_mode,
                                        "detected_at": datetime.utcnow().isoformat(),
                                    }
                                )
                            except Exception as callback_error:
                                logger.warning(
                                    "No se pudo registrar la desconexión de %s:%s: %s",
                                    target_ip,
                                    target_port,
                                    callback_error,
                                )

                    raise DeviceDisconnectedDuringSyncError(
                        details={
                            "ip": target_ip,
                            "port": target_port,
                            "stage": "device_read",
                            "reason": monitor_state.reason,
                            "probe_mode": monitor_state.probe_mode,
                            "original_error": str(e),
                        }
                    ) from e

                log_exception(logger, e, "Error al obtener datos del reloj")
                raise
            finally:
                ZKService._stop_sync_monitor(monitor_state)
                if conn:
                    ZKService._disconnect(conn)

    @staticmethod
    def create_user(
        uid: int,
        user_id: str = None,
        name: str = "",
        role: str = "usuario",
        ip: str = None,
        port: int = None,
        password: str = None,
    ) -> Dict[str, Any]:
        """
        Crea un usuario en el dispositivo después de comprobar que no exista un duplicado.

        :param uid: UID del usuario en el dispositivo.
        :type uid: int
        :param user_id: Identificador del usuario.
        :type user_id: str
        :param name: Nombre del usuario.
        :type name: str
        :param role: Rol que se debe convertir.
        :type role: str
        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :param password: Contraseña opcional de comunicación del dispositivo.
        :type password: str
        :return: Resultado de la creación y datos del usuario.
        :rtype: dict[str, Any]
        :raises DuplicateUserError: Si el UID o el identificador del usuario ya están registrados.
        """
        from app.exceptions import DuplicateUserError

        conn = None

        try:
            conn = ZKService._create_connection(ip, port, password)
            user_id = normalize_user_id(user_id or uid)

            usuarios = conn.get_users()

            for usuario in usuarios:
                if int(usuario.uid) == int(uid):
                    raise DuplicateUserError(f"Usuario con UID {uid} ya existe")

                if normalize_user_id(usuario.user_id) == user_id:
                    raise DuplicateUserError(f"User ID '{user_id}' ya está registrado")

            privilege = role_to_privilege(role)

            logger.info(
                "Creando usuario en reloj: uid=%s user_id=%s name=%s role=%s privilege=%s",
                uid,
                user_id,
                name,
                role,
                privilege,
            )

            conn.set_user(
                uid=int(uid),
                name=str(name),
                privilege=privilege,
                password="",
                group_id="",
                user_id=str(user_id),
            )

            try:
                conn.refresh_data()
            except Exception as e:
                logger.warning(
                    "No se pudo refrescar datos del reloj, pero el usuario pudo haberse creado: %s",
                    e,
                )

            return {
                "message": f"Usuario '{name}' creado exitosamente",
                "user": {
                    "uid": uid,
                    "user_id": user_id,
                    "name": name,
                    "role": role,
                },
            }

        except DuplicateUserError:
            raise

        except Exception as e:
            logger.exception("Error real al crear usuario en reloj")
            raise

        finally:
            if conn:
                try:
                    conn.enable_device()
                except Exception as e:
                    logger.warning("No se pudo reactivar el reloj: %s", e)

                try:
                    ZKService._disconnect(conn)
                except Exception as e:
                    logger.warning("No se pudo cerrar la conexión, se ignora: %s", e)

    @staticmethod
    def create_user_with_next_uid(
        name: str,
        role: str = "usuario",
        minimum_uid: int = 1,
        ip: str = None,
        port: int = None,
        password: str = None,
    ) -> Dict[str, Any]:
        """
        Crea un usuario utilizando el siguiente UID disponible en el dispositivo.

        :param name: Nombre del usuario.
        :type name: str
        :param role: Rol que se debe convertir.
        :type role: str
        :param minimum_uid: UID mínimo que se debe considerar para la nueva asignación.
        :type minimum_uid: int
        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :param password: Contraseña opcional de comunicación del dispositivo.
        :type password: str
        :return: Resultado de la creación y datos del usuario.
        :rtype: dict[str, Any]
        """
        conn = None

        try:
            conn = ZKService._create_connection(ip, port, password)
            usuarios = conn.get_users()

            used_uids = {int(usuario.uid) for usuario in usuarios}
            used_user_ids = {
                normalize_user_id(usuario.user_id) for usuario in usuarios
            }

            highest_uid = max(used_uids, default=0)
            next_uid = max(highest_uid + 1, int(minimum_uid or 1))

            while (
                next_uid in used_uids
                or str(next_uid) in used_user_ids
            ):
                next_uid += 1

            user_id = str(next_uid)
            privilege = role_to_privilege(role)

            logger.info(
                "Creando copia de usuario en reloj: uid=%s name=%s role=%s",
                next_uid,
                name,
                role,
            )

            conn.set_user(
                uid=next_uid,
                name=str(name),
                privilege=privilege,
                password="",
                group_id="",
                user_id=user_id,
            )

            try:
                conn.refresh_data()
            except Exception as e:
                logger.warning(
                    "No se pudo refrescar datos del reloj tras copiar usuario: %s",
                    e,
                )

            return {
                "message": f"Usuario '{name}' creado exitosamente",
                "user": {
                    "uid": next_uid,
                    "user_id": user_id,
                    "name": name,
                    "role": role,
                },
            }
        finally:
            if conn:
                try:
                    ZKService._disconnect(conn)
                except Exception as e:
                    logger.warning(
                        "No se pudo cerrar la conexion tras copiar usuario: %s",
                        e,
                    )

    @staticmethod
    def update_user(
        uid: int,
        user_id: str = None,
        name: str = None,
        role: str = None,
        ip: str = None,
        port: int = None,
        password: str = None,
    ) -> Dict[str, Any]:
        """
        Actualiza los datos de un usuario existente en el dispositivo.

        :param uid: UID del usuario en el dispositivo.
        :type uid: int
        :param user_id: Identificador del usuario.
        :type user_id: str
        :param name: Nombre del usuario.
        :type name: str
        :param role: Rol que se debe convertir.
        :type role: str
        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :param password: Contraseña opcional de comunicación del dispositivo.
        :type password: str
        :return: Resultado de la actualización y datos del usuario.
        :rtype: dict[str, Any]
        :raises ValueError: Si no existe un usuario con el UID indicado.
        """
        conn = None

        try:
            conn = ZKService._create_connection(ip, port, password)
            usuarios = conn.get_users()

            usuario_actual = None

            for usuario in usuarios:
                if int(usuario.uid) == int(uid):
                    usuario_actual = usuario
                    break

            if not usuario_actual:
                raise ValueError(f"Usuario con UID {uid} no encontrado")

            nuevo_user_id = normalize_user_id(user_id if user_id else usuario_actual.user_id)
            nuevo_name = name if name else usuario_actual.name
            nuevo_role = role if role else privilege_to_role(getattr(usuario_actual, "privilege", 0))

            conn.set_user(
                uid=int(uid),
                name=nuevo_name,
                privilege=role_to_privilege(nuevo_role),
                password="",
                group_id="",
                user_id=nuevo_user_id,
            )

            return {
                "message": f"Usuario {uid} actualizado exitosamente",
                "user": {
                    "uid": uid,
                    "user_id": nuevo_user_id,
                    "name": nuevo_name,
                    "role": nuevo_role,
                },
            }

        finally:
            if conn:
                ZKService._disconnect(conn)

    @staticmethod
    def delete_user(uid: int, ip: str = None, port: int = None, password: str = None) -> Dict[str, Any]:
        """
        Elimina un usuario del dispositivo mediante su UID.

        :param uid: UID del usuario en el dispositivo.
        :type uid: int
        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :param password: Contraseña opcional de comunicación del dispositivo.
        :type password: str
        :return: Resultado de la eliminación.
        :rtype: dict[str, Any]
        :raises ValueError: Si no existe un usuario con el UID indicado.
        """
        conn = None

        try:
            conn = ZKService._create_connection(ip, port, password)
            usuarios = conn.get_users()

            usuario_encontrado = False

            for usuario in usuarios:
                if int(usuario.uid) == int(uid):
                    usuario_encontrado = True
                    break

            if not usuario_encontrado:
                raise ValueError(f"Usuario con UID {uid} no existe")

            conn.delete_user(uid)

            return {
                "message": f"Usuario {uid} eliminado exitosamente",
            }

        finally:
            if conn:
                ZKService._disconnect(conn)

    @staticmethod
    def get_attendance_records(
        ip: str = None,
        port: int = None,
        password: str = None,
        on_disconnect: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene los registros de asistencia mediante una lectura completa vigilada.

        :param ip: Dirección IP opcional del dispositivo.
        :type ip: str
        :param port: Puerto opcional de comunicación del dispositivo.
        :type port: int
        :param password: Contraseña opcional de comunicación del dispositivo.
        :type password: str
        :param on_disconnect: Función opcional invocada cuando se detecta una desconexión.
        :type on_disconnect: Callable[[Dict[str, Any]], None] or None
        :return: Lista de registros de asistencia normalizados.
        :rtype: list[dict[str, Any]]
        """
        snapshot = ZKService.get_sync_snapshot(
            ip,
            port,
            password,
            on_disconnect=on_disconnect,
        )
        return snapshot["attendance"]