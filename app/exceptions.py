"""Excepciones de dominio usadas por TimeCore.

Cada excepción incluye un código estable, un mensaje seguro para el cliente y
un status HTTP. Así las rutas no tienen que repetir el mismo manejo de errores.
"""
from __future__ import annotations

from typing import Any


class TimeCoreError(Exception):
    """
    Representa la excepción base controlada de TimeCore.

    Permite definir un mensaje seguro, detalles adicionales, un código de error
    estable y un estado HTTP asociado.
    """

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
        """
        Inicializa una excepción controlada de TimeCore.

        :param message: Mensaje opcional que describe el error.
        :type message: str or None
        :param details: Información adicional relacionada con el error.
        :type details: Any
        :param status_code: Estado HTTP opcional que reemplaza el valor predeterminado.
        :type status_code: int or None
        :param code: Código opcional que reemplaza el código de error predeterminado.
        :type code: str or None
        :return: No devuelve ningún valor.
        :rtype: None
        """
        self.message = message or self.default_message
        self.details = details
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        super().__init__(self.message)


class DataValidationError(TimeCoreError):
    """
    Indica que los datos recibidos no cumplen las reglas de validación.
    """
    status_code = 400
    code = "DATA_VALIDATION_ERROR"
    default_message = "Los datos enviados no son válidos"


class AuthenticationError(TimeCoreError):
    """
    Indica que no fue posible autenticar la sesión.
    """
    status_code = 401
    code = "AUTHENTICATION_ERROR"
    default_message = "No fue posible autenticar la sesión"


class AuthorizationError(TimeCoreError):
    """
    Indica que el usuario no tiene permisos para realizar una operación.
    """
    status_code = 403
    code = "AUTHORIZATION_ERROR"
    default_message = "No tienes permisos para realizar esta acción"


class ResourceNotFoundError(TimeCoreError):
    """
    Indica que el recurso solicitado no fue encontrado.
    """
    status_code = 404
    code = "RESOURCE_NOT_FOUND"
    default_message = "El recurso solicitado no existe"


class ConflictError(TimeCoreError):
    """
    Indica que una operación entra en conflicto con los datos existentes.
    """
    status_code = 409
    code = "CONFLICT_ERROR"
    default_message = "La operación entra en conflicto con los datos existentes"


class DuplicateUserError(ConflictError):
    """
    Indica que se intentó registrar un usuario que ya existe.
    """
    code = "DUPLICATE_USER"
    default_message = "El usuario ya existe"


class DatabaseError(TimeCoreError):
    """
    Indica que ocurrió un error durante una operación de base de datos.
    """
    status_code = 500
    code = "DATABASE_ERROR"
    default_message = "No fue posible completar la operación en la base de datos"


class DeviceUnavailableError(TimeCoreError):
    """
    Indica que el reloj biométrico no está disponible.
    """
    status_code = 503
    code = "DEVICE_UNAVAILABLE"
    default_message = "El reloj no está disponible"


class DeviceAuthenticationError(TimeCoreError):
    """
    Indica que el reloj rechazó la contraseña de comunicación.
    """
    status_code = 503
    code = "DEVICE_AUTHENTICATION_ERROR"
    default_message = "El reloj rechazó la contraseña de comunicación"


class DeviceTimeoutError(TimeCoreError):
    """
    Indica que el reloj superó el tiempo máximo de respuesta.
    """
    status_code = 504
    code = "DEVICE_TIMEOUT"
    default_message = "El reloj tardó demasiado en responder"


class DeviceDisconnectedDuringSyncError(TimeCoreError):
    """
    Indica que el reloj fue desconectado durante una sincronización.
    """
    status_code = 503
    code = "DEVICE_DISCONNECTED_DURING_SYNC"
    default_message = (
        "La sincronización fue cancelada porque el reloj fue desconectado."
    )


class DeviceClockDriftError(TimeCoreError):
    """
    Indica que la fecha y hora del reloj presentan un desfase no permitido.
    """
    status_code = 409
    code = "DEVICE_CLOCK_DRIFT"
    default_message = (
        "La fecha y hora del reloj no coinciden con el servidor. "
        "Corrige la hora antes de sincronizar asistencias."
    )


class ZKError(DeviceUnavailableError):
    """
    Indica que ocurrió un error de comunicación con el reloj ZKTeco.
    """
    code = "ZK_COMMUNICATION_ERROR"
    default_message = "Ocurrió un error de comunicación con el reloj"


class SyncError(TimeCoreError):
    """
    Indica que no fue posible completar la sincronización del reloj.
    """
    status_code = 502
    code = "SYNC_ERROR"
    default_message = "No fue posible sincronizar la información del reloj"