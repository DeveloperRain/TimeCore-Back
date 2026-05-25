from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime

class UserCreate(BaseModel):
    uid: int = Field(..., gt=0, description="ID único del usuario (debe ser positivo)")
    user_id: str = Field(..., min_length=1, max_length=50, description="ID del usuario en el reloj")
    name: str = Field(..., min_length=1, max_length=100, description="Nombre completo del usuario")

    class Config:
        examples = [{
            "uid": 1,
            "user_id": "001",
            "name": "Juan García"
        }]

class UserUpdate(BaseModel):
    uid: Optional[int] = Field(None, gt=0, description="ID único del usuario")
    user_id: Optional[str] = Field(None, min_length=1, max_length=50, description="ID del usuario en el reloj")
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Nombre completo del usuario")

    class Config:
        examples = [{
            "name": "Juan García Pérez"
        }]

class UserResponse(BaseModel):
    uid: int = Field(..., description="ID único del usuario")
    user_id: str = Field(..., description="ID del usuario en el reloj")
    name: str = Field(..., description="Nombre del usuario")

    class Config:
        examples = [{
            "uid": 1,
            "user_id": "001",
            "name": "Juan García"
        }]

class NetworkParams(BaseModel):
    ip: str = Field(..., description="Dirección IP del dispositivo")
    gateway: str = Field(..., description="Puerta de enlace")
    dns: str = Field(..., description="Servidor DNS")

class DeviceInfo(BaseModel):
    name: str = Field(..., description="Nombre del dispositivo")
    serial: str = Field(..., description="Número de serie")
    firmware: str = Field(..., description="Versión del firmware")
    mac_address: str = Field(..., description="Dirección MAC del dispositivo")
    device_time: str = Field(..., description="Hora actual del dispositivo")
    network_params: NetworkParams = Field(..., description="Parámetros de red")

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
    user_id: str = Field(..., description="ID del usuario")
    timestamp: str = Field(..., description="Fecha y hora de la asistencia")
    status: str = Field(..., description="Estado de la asistencia")

    class Config:
        examples = [{
            "user_id": "001",
            "timestamp": "2026-05-25 08:45:30",
            "status": "in"
        }]

class ErrorResponse(BaseModel):
    error: str = Field(..., description="Mensaje de error")
    code: Optional[str] = Field(None, description="Código de error")

    class Config:
        examples = [{
            "error": "Usuario no encontrado",
            "code": "USER_NOT_FOUND"
        }]
