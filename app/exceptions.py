"""Excepciones de dominio usadas por TimeCore.

Cada excepción incluye un código estable, un mensaje seguro para el cliente y
un status HTTP. Así las rutas no tienen que repetir el mismo manejo de errores.
"""
from __future__ import annotations

from typing import Any


class TimeCoreError(Exception):
    """Excepción base controlada de la aplicación."""

    status_code = 400
    code = "TIMECORE_ERROR"
    default_message = "No se pudo completar la operación"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Any = None,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        super().__init__(self.message)


class DataValidationError(TimeCoreError):
    status_code = 400
    code = "DATA_VALIDATION_ERROR"
    default_message = "Los datos enviados no son válidos"


class AuthenticationError(TimeCoreError):
    status_code = 401
    code = "AUTHENTICATION_ERROR"
    default_message = "No fue posible autenticar la sesión"


class AuthorizationError(TimeCoreError):
    status_code = 403
    code = "AUTHORIZATION_ERROR"
    default_message = "No tienes permisos para realizar esta acción"


class ResourceNotFoundError(TimeCoreError):
    status_code = 404
    code = "RESOURCE_NOT_FOUND"
    default_message = "El recurso solicitado no existe"


class ConflictError(TimeCoreError):
    status_code = 409
    code = "CONFLICT_ERROR"
    default_message = "La operación entra en conflicto con los datos existentes"


class DuplicateUserError(ConflictError):
    code = "DUPLICATE_USER"
    default_message = "El usuario ya existe"


class DatabaseError(TimeCoreError):
    status_code = 500
    code = "DATABASE_ERROR"
    default_message = "No fue posible completar la operación en la base de datos"


class DeviceUnavailableError(TimeCoreError):
    status_code = 503
    code = "DEVICE_UNAVAILABLE"
    default_message = "El reloj no está disponible"


class DeviceAuthenticationError(TimeCoreError):
    status_code = 503
    code = "DEVICE_AUTHENTICATION_ERROR"
    default_message = "El reloj rechazó la contraseña de comunicación"


class DeviceTimeoutError(TimeCoreError):
    status_code = 504
    code = "DEVICE_TIMEOUT"
    default_message = "El reloj tardó demasiado en responder"


class DeviceDisconnectedDuringSyncError(TimeCoreError):
    status_code = 503
    code = "DEVICE_DISCONNECTED_DURING_SYNC"
    default_message = (
        "La sincronización fue cancelada porque el reloj fue desconectado."
    )


class DeviceClockDriftError(TimeCoreError):
    status_code = 409
    code = "DEVICE_CLOCK_DRIFT"
    default_message = (
        "La fecha y hora del reloj no coinciden con el servidor. "
        "Corrige la hora antes de sincronizar asistencias."
    )


class ZKError(DeviceUnavailableError):
    code = "ZK_COMMUNICATION_ERROR"
    default_message = "Ocurrió un error de comunicación con el reloj"


class SyncError(TimeCoreError):
    status_code = 502
    code = "SYNC_ERROR"
    default_message = "No fue posible sincronizar la información del reloj"
