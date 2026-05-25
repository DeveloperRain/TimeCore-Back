from zk import ZK
from typing import List, Dict, Any
import socket

IP_RELOJ = "192.168.1.50"
PORT = 4370
TIMEOUT = 10

class ZKService:
    @staticmethod
    def _create_connection():
        try:
            zk = ZK(IP_RELOJ, port=PORT, timeout=TIMEOUT)
            conn = zk.connect()
            return conn
        except socket.timeout:
            raise TimeoutError("Conexión agotada con el dispositivo")
        except ConnectionRefusedError:
            raise ConnectionError("El dispositivo rechazó la conexión")
        except Exception as e:
            raise Exception(f"Error de conexión: {str(e)}")

    @staticmethod
    def get_device_info() -> Dict[str, Any]:
        conn = None
        try:
            conn = ZKService._create_connection()
            device = conn.get_device_info()

            device_info = {
                "name": getattr(device, 'name', "Desconocido"),
                "serial": getattr(device, 'serial', "Desconocido"),
                "firmware": getattr(device, 'firmware', "Desconocido"),
                "mac_address": getattr(device, 'mac', "Desconocido"),
                "device_time": str(getattr(device, 'device_time', "Desconocido")),
                "network_params": {
                    "ip": getattr(device, 'ip', "Desconocido"),
                    "gateway": getattr(device, 'gateway', "Desconocido"),
                    "dns": getattr(device, 'dns', "Desconocido"),
                }
            }
            return device_info
        finally:
            if conn:
                conn.disconnect()

    @staticmethod
    def get_all_users() -> List[Dict[str, Any]]:
        conn = None
        try:
            conn = ZKService._create_connection()
            usuarios = conn.get_users()

            response = [
                {
                    "uid": u.uid,
                    "user_id": u.user_id,
                    "name": u.name
                }
                for u in usuarios
            ]
            return response
        finally:
            if conn:
                conn.disconnect()

    @staticmethod
    def create_user(uid: int, user_id: str, name: str) -> Dict[str, Any]:
        conn = None
        try:
            conn = ZKService._create_connection()
            conn.set_user(
                uid=uid,
                name=name,
                password=' ',
                group_id=' ',
                user_id=user_id
            )
            return {
                "message": f"Usuario '{name}' creado exitosamente",
                "user": {"uid": uid, "user_id": user_id, "name": name}
            }
        finally:
            if conn:
                conn.disconnect()

    @staticmethod
    def update_user(uid: int, user_id: str = None, name: str = None) -> Dict[str, Any]:
        conn = None
        try:
            conn = ZKService._create_connection()
            usuarios = conn.get_users()

            usuario_actual = None
            for u in usuarios:
                if u.uid == uid:
                    usuario_actual = u
                    break

            if not usuario_actual:
                raise ValueError(f"Usuario con UID {uid} no encontrado")

            nuevo_user_id = user_id if user_id else usuario_actual.user_id
            nuevo_name = name if name else usuario_actual.name

            conn.set_user(
                uid=uid,
                name=nuevo_name,
                password=' ',
                group_id=' ',
                user_id=nuevo_user_id
            )

            return {
                "message": f"Usuario {uid} actualizado exitosamente",
                "user": {"uid": uid, "user_id": nuevo_user_id, "name": nuevo_name}
            }
        finally:
            if conn:
                conn.disconnect()

    @staticmethod
    def delete_user(uid: int) -> Dict[str, Any]:
        conn = None
        try:
            conn = ZKService._create_connection()
            conn.delete_user(uid)
            return {"message": f"Usuario {uid} eliminado exitosamente"}
        finally:
            if conn:
                conn.disconnect()

    @staticmethod
    def get_attendance_records() -> List[Dict[str, Any]]:
        conn = None
        try:
            conn = ZKService._create_connection()
            asistencias = conn.get_attendance()

            response = [
                {
                    "user_id": a.user_id,
                    "timestamp": str(a.timestamp),
                    "status": a.status
                }
                for a in asistencias
            ]
            return response
        finally:
            if conn:
                conn.disconnect()
