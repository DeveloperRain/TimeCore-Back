import socket
import threading
from contextlib import contextmanager
from typing import Any, Dict, List

from zk import ZK

from app.config.logger import get_logger, log_exception
from app.exceptions import DeviceAuthenticationError, DeviceTimeoutError, DeviceUnavailableError

IP_RELOJ = "192.168.1.50"
PORT = 4370
TIMEOUT = 30
PASSWORD = 10

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
    return ROLE_PRIVILEGES.get(role, ROLE_PRIVILEGES["usuario"])


def privilege_to_role(privilege) -> str:
    try:
        return "admin" if int(privilege) == ROLE_PRIVILEGES["admin"] else "usuario"
    except (TypeError, ValueError):
        return "usuario"


def normalize_user_id(user_id) -> str:
    return str(user_id).strip()


def normalize_attendance_status(status, punch=None) -> str:
    """Normaliza el tipo de marcación reportado por distintos modelos ZKTeco.

    Algunos equipos colocan el valor útil en ``punch`` y devuelven 255 o None
    en ``status``. Se usa ``status`` cuando es reconocido y, si no, ``punch``.
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


def call_if_available(conn, method_name: str, default: str = "Desconocido"):
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
    _device_locks: Dict[str, threading.RLock] = {}
    _device_locks_guard = threading.Lock()

    @staticmethod
    def _device_key(ip: str = None, port: int = None) -> str:
        return f"{ip or IP_RELOJ}:{int(port or PORT)}"

    @staticmethod
    def _get_device_lock(ip: str = None, port: int = None) -> threading.RLock:
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
        lock = ZKService._get_device_lock(ip, port)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    @staticmethod
    def check_device_status(ip: str, port: int = PORT, timeout: int = 2) -> bool:
        # No se abre otra conexión mientras el mismo reloj está sincronizando.
        # Si el candado está ocupado, la sincronización ya confirmó comunicación.
        lock = ZKService._get_device_lock(ip, port)
        if not lock.acquire(blocking=False):
            return True

        try:
            with socket.create_connection((ip, port or PORT), timeout=timeout):
                return True
        except Exception as e:
            logger.warning("Reloj %s:%s sin conexion: %s", ip, port, e)
            return False
        finally:
            lock.release()

    @staticmethod
    def _create_connection(ip: str = None, port: int = None, password: str = None):
        target_ip = ip or IP_RELOJ
        target_port = int(port or PORT)

        try:
            target_password = int(password if password not in (None, "") else PASSWORD)
        except (TypeError, ValueError):
            target_password = 0

        attempts = [
            {"force_udp": False, "ommit_ping": False, "label": "TCP"},
            {"force_udp": False, "ommit_ping": True, "label": "TCP sin ping"},
            {"force_udp": True, "ommit_ping": False, "label": "UDP"},
            {"force_udp": True, "ommit_ping": True, "label": "UDP sin ping"},
        ]

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
                    timeout=TIMEOUT,
                    password=target_password,
                    force_udp=attempt["force_udp"],
                    ommit_ping=attempt["ommit_ping"],
                )

                conn = zk.connect()
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
        try:
            conn.disconnect()
        except Exception as e:
            logger.warning("No se pudo cerrar la conexion con el reloj: %s", e)

    @staticmethod
    def get_device_info(ip: str = None, port: int = None, password: str = None) -> Dict[str, Any]:
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
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Lee usuarios y asistencias usando una sola sesión del reloj.

        Evita abrir dos conexiones consecutivas durante una sincronización y
        bloquea los sondeos de estado del mismo reloj mientras se descargan los
        datos. Esto es importante porque varios modelos ZKTeco toleran una sola
        sesión estable a la vez.
        """
        conn = None
        disabled = False

        with ZKService._locked_device(ip, port):
            try:
                conn = ZKService._create_connection(ip, port, password)

                try:
                    conn.disable_device()
                    disabled = True
                except Exception as e:
                    logger.warning(
                        "No se pudo bloquear temporalmente el reloj para lectura: %s",
                        e,
                    )

                # get_attendance() de pyzk ya consulta internamente los usuarios.
                # Se lee primero para obtener el log más reciente y después se
                # consulta la lista de usuarios para enriquecer nombre y UID.
                attendance_objects = conn.get_attendance() or []
                user_objects = conn.get_users() or []

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

                latest = sorted(
                    attendance,
                    key=lambda value: value.get("timestamp"),
                )[-5:]
                logger.info(
                    "Lectura del reloj %s:%s: %s usuarios, %s asistencias. Últimas: %s",
                    ip or IP_RELOJ,
                    int(port or PORT),
                    len(users),
                    len(attendance),
                    latest,
                )

                return {"users": users, "attendance": attendance}

            except Exception as e:
                log_exception(logger, e, "Error al obtener datos del reloj")
                raise
            finally:
                if conn:
                    if disabled:
                        try:
                            conn.enable_device()
                        except Exception as e:
                            logger.warning(
                                "No se pudo reactivar el reloj después de leer: %s",
                                e,
                            )
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
        """Crea un usuario usando la siguiente UID real del reloj.

        Consulta los usuarios y crea la nueva asignacion dentro de la misma
        conexion para reducir colisiones y sesiones simultaneas.
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
    def get_attendance_records(ip: str = None, port: int = None, password: str = None) -> List[Dict[str, Any]]:
        snapshot = ZKService.get_sync_snapshot(ip, port, password)
        return snapshot["attendance"]
