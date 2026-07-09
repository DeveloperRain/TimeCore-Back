"""Validador de datos del reloj y BD."""
from datetime import datetime
from app.exceptions import DataValidationError

class DataValidator:
    """Valida integridad de datos antes de guardar."""

    VALID_STATUSES = ["check_in", "check_out", "break_in", "break_out", "overtime_in", "overtime_out"]
    VALID_ROLES = ["usuario", "admin"]

    @staticmethod
    def validate_user(uid: int, user_id: str, name: str, role: str) -> None:
        """Valida datos de usuario."""
        if uid is None or uid <= 0 or uid > 999999:
            raise DataValidationError(f"UID inválido: {uid} (debe ser 1-999999)")
        if not user_id or len(user_id) > 50:
            raise DataValidationError(f"user_id inválido: {user_id} (máximo 50 caracteres)")
        if not user_id.strip():
            raise DataValidationError("user_id no puede estar vacío")
        if not name or len(name) > 100:
            raise DataValidationError(f"name inválido: {name} (máximo 100 caracteres)")
        if not name.strip():
            raise DataValidationError("name no puede estar vacío")
        if role not in DataValidator.VALID_ROLES:
            raise DataValidationError(f"role inválido: {role} (debe ser 'usuario' o 'admin')")

    @staticmethod
    def validate_attendance(uid: int, user_id: str, name: str, timestamp: datetime, status: str) -> None:
        """Valida registro de asistencia."""
        if uid is not None and (uid <= 0 or uid > 999999):
            raise DataValidationError(f"UID en asistencia inválido: {uid}")
        if not user_id:
            raise DataValidationError("user_id requerido en asistencia")
        if not timestamp:
            raise DataValidationError("timestamp requerido en asistencia")
        if not isinstance(timestamp, datetime):
            raise DataValidationError(f"timestamp debe ser datetime, recibido: {type(timestamp)}")
        if timestamp > datetime.utcnow():
            raise DataValidationError(f"timestamp no puede ser en el futuro: {timestamp}")
        if status not in DataValidator.VALID_STATUSES:
            raise DataValidationError(f"status inválido: {status}. Valores válidos: {DataValidator.VALID_STATUSES}")

    @staticmethod
    def validate_date_range(start_date: datetime, end_date: datetime) -> None:
        """Valida rango de fechas."""
        if start_date > end_date:
            raise DataValidationError("Fecha inicial no puede ser mayor que fecha final")
        if end_date > datetime.utcnow():
            raise DataValidationError("Fecha final no puede ser en el futuro")

    @staticmethod
    def validate_pagination(page: int, limit: int) -> None:
        """Valida parámetros de paginación."""
        if page < 1:
            raise DataValidationError("page debe ser mayor o igual a 1")
        if limit < 1 or limit > 100:
            raise DataValidationError("limit debe estar entre 1 y 100")
