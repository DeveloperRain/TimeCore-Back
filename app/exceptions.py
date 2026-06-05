"""Excepciones personalizadas de la aplicación."""

class ZKError(Exception):
    """Error en comunicación con reloj ZKTeco."""
    pass

class DataValidationError(Exception):
    """Error en validación de datos."""
    pass

class DuplicateUserError(Exception):
    """Error cuando intenta crear un usuario que ya existe."""
    pass

class SyncError(Exception):
    """Error en sincronización ZK-BD."""
    pass

