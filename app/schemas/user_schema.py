from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


UserRole = Literal["usuario", "admin"]


class UserCreate(BaseModel):
    uid: int = Field(..., gt=0, description="ID unico del usuario (debe ser positivo)")
    user_id: str = Field(..., min_length=1, max_length=50, description="ID del usuario en el reloj")
    name: str = Field(..., min_length=1, max_length=100, description="Nombre completo del usuario")
    role: UserRole = Field("usuario", description="Rol del usuario en el reloj")

    @field_validator("user_id", "name")
    @classmethod
    def clean_text_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El campo no puede estar vacio")
        return value

    class Config:
        examples = [{
            "uid": 1,
            "user_id": "001",
            "name": "Juan Garcia",
            "role": "usuario"
        }]


class UserUpdate(BaseModel):
    uid: Optional[int] = Field(None, gt=0, description="ID unico del usuario")
    user_id: Optional[str] = Field(None, min_length=1, max_length=50, description="ID del usuario en el reloj")
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Nombre completo del usuario")
    role: Optional[UserRole] = Field(None, description="Rol del usuario en el reloj")

    @field_validator("user_id", "name")
    @classmethod
    def clean_text_fields(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        value = value.strip()
        if not value:
            raise ValueError("El campo no puede estar vacio")
        return value

    class Config:
        examples = [{
            "name": "Juan Garcia Perez",
            "role": "admin"
        }]


class UserResponse(BaseModel):
    uid: int = Field(..., description="ID unico del usuario")
    user_id: str = Field(..., description="ID del usuario en el reloj")
    name: str = Field(..., description="Nombre del usuario")
    role: UserRole = Field(..., description="Rol del usuario en el reloj")

    class Config:
        examples = [{
            "uid": 1,
            "user_id": "001",
            "name": "Juan Garcia",
            "role": "usuario"
        }]


class NetworkParams(BaseModel):
    ip: str = Field(..., description="Direccion IP del dispositivo")
    gateway: str = Field(..., description="Puerta de enlace")
    dns: str = Field(..., description="Servidor DNS")


class DeviceInfo(BaseModel):
    name: str = Field(..., description="Nombre del dispositivo")
    serial: str = Field(..., description="Numero de serie")
    firmware: str = Field(..., description="Version del firmware")
    mac_address: str = Field(..., description="Direccion MAC del dispositivo")
    device_time: str = Field(..., description="Hora actual del dispositivo")
    network_params: NetworkParams = Field(..., description="Parametros de red")

    class Config:
        examples = [{
            "name": "ZK9500",
            "serial": "123456789",
            "firmware": "v1.2.3",
            "mac_address": "00:11:22:33:44:55",
            "device_time": "2026-05-25 22:35:00",
            "network_params": {
                "ip": "192.168.1.50",
                "gateway": "192.168.1.1",
                "dns": "8.8.8.8"
            }
        }]


class AttendanceRecord(BaseModel):
    name: str = Field(..., description="Nombre del usuario")
    user_id: str = Field(..., description="ID del usuario")
    timestamp: str = Field(..., description="Fecha y hora de la asistencia")
    status: str = Field(..., description="Estado de la asistencia")

    class Config:
        examples = [{
            "name": "Juan Garcia",
            "user_id": "001",
            "timestamp": "2026-05-25 08:45:30",
            "status": "check_in"
        }]


class ErrorResponse(BaseModel):
    error: str = Field(..., description="Mensaje de error")
    code: Optional[str] = Field(None, description="Codigo de error")

    class Config:
        examples = [{
            "error": "Usuario no encontrado",
            "code": "USER_NOT_FOUND"
        }]
