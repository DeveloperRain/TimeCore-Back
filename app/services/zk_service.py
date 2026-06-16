import socket
from typing import Any, Dict, List

from zk import ZK

from app.config.logger import get_logger, log_exception

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
    @staticmethod
    def _create_connection(ip: str = None, port: int = None):
        target_ip = ip or IP_RELOJ
        target_port = port or PORT

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
                    password=PASSWORD,
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

        if isinstance(last_error, socket.timeout):
            log_exception(logger, last_error, "Tiempo agotado conectando al reloj")
            raise TimeoutError("Conexion agotada con el dispositivo")

        if isinstance(last_error, ConnectionRefusedError):
            log_exception(logger, last_error, "El reloj rechazo la conexion")
            raise ConnectionError("El dispositivo rechazo la conexion")

        log_exception(logger, last_error, "Error de conexion con el reloj")
        raise ConnectionError(f"Error de conexion: {str(last_error)}")

    @staticmethod
    def _disconnect(conn):
        try:
            conn.disconnect()
        except Exception as e:
            logger.warning("No se pudo cerrar la conexion con el reloj: %s", e)

    @staticmethod
    def get_device_info(ip: str = None, port: int = None) -> Dict[str, Any]:
        conn = None
        target_ip = ip or IP_RELOJ

        try:
            conn = ZKService._create_connection(ip, port)

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
    def get_all_users(ip: str = None, port: int = None) -> List[Dict[str, Any]]:
        conn = None

        try:
            conn = ZKService._create_connection(ip, port)
            usuarios = conn.get_users()

            return [
                {
                    "uid": u.uid,
                    "user_id": normalize_user_id(u.user_id),
                    "name": u.name,
                    "role": privilege_to_role(getattr(u, "privilege", 0)),
                }
                for u in usuarios
            ]

        finally:
            if conn:
                ZKService._disconnect(conn)

    @staticmethod
    def create_user(
        uid: int,
        user_id: str,
        name: str,
        role: str = "usuario",
        ip: str = None,
        port: int = None,
    ) -> Dict[str, Any]:
        from app.exceptions import DuplicateUserError

        conn = None

        try:
            conn = ZKService._create_connection(ip, port)
            user_id = normalize_user_id(user_id)

            usuarios = conn.get_users()

            for usuario in usuarios:
                if usuario.uid == uid:
                    raise DuplicateUserError(f"Usuario con UID {uid} ya existe")

                if normalize_user_id(usuario.user_id) == user_id:
                    raise DuplicateUserError(f"User ID '{user_id}' ya está registrado")

            conn.set_user(
                uid=uid,
                name=name,
                privilege=role_to_privilege(role),
                password="",
                group_id="",
                user_id=user_id,
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

        finally:
            if conn:
                ZKService._disconnect(conn)

    @staticmethod
    def update_user(
        uid: int,
        user_id: str = None,
        name: str = None,
        role: str = None,
        ip: str = None,
        port: int = None,
    ) -> Dict[str, Any]:
        conn = None

        try:
            conn = ZKService._create_connection(ip, port)
            usuarios = conn.get_users()

            usuario_actual = None

            for usuario in usuarios:
                if usuario.uid == uid:
                    usuario_actual = usuario
                    break

            if not usuario_actual:
                raise ValueError(f"Usuario con UID {uid} no encontrado")

            nuevo_user_id = normalize_user_id(user_id if user_id else usuario_actual.user_id)
            nuevo_name = name if name else usuario_actual.name
            nuevo_role = role if role else privilege_to_role(getattr(usuario_actual, "privilege", 0))

            conn.set_user(
                uid=uid,
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
    def delete_user(uid: int, ip: str = None, port: int = None) -> Dict[str, Any]:
        conn = None

        try:
            conn = ZKService._create_connection(ip, port)
            usuarios = conn.get_users()

            usuario_encontrado = False

            for usuario in usuarios:
                if usuario.uid == uid:
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
    def get_attendance_records(ip: str = None, port: int = None) -> List[Dict[str, Any]]:
        conn = None

        try:
            conn = ZKService._create_connection(ip, port)
            usuarios = conn.get_users()
            asistencias = conn.get_attendance()

            users_by_id = {
                normalize_user_id(usuario.user_id): {
                    "uid": usuario.uid,
                    "name": usuario.name,
                }
                for usuario in usuarios
            }

            return [
                {
                    "uid": users_by_id.get(normalize_user_id(a.user_id), {}).get("uid"),
                    "user_id": normalize_user_id(a.user_id),
                    "name": users_by_id.get(
                        normalize_user_id(a.user_id),
                        {},
                    ).get("name", "Desconocido"),
                    "timestamp": str(a.timestamp),
                    "status": ATTENDANCE_STATUS.get(a.status, str(a.status)),
                }
                for a in asistencias
            ]

        except Exception as e:
            log_exception(logger, e, "Error al obtener asistencias del reloj")
            raise

        finally:
            if conn:
                ZKService._disconnect(conn)