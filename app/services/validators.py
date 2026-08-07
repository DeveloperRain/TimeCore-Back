"""Validador de datos del reloj y BD."""
from datetime import datetime
from app.exceptions import DataValidationError

class DataValidator:
    """Valida integridad de datos antes de guardar."""

    VALID_STATUSES = ["check_in", "check_out", "break_in", "break_out", "overtime_in", "overtime_out"]
    VALID_ROLES = ["usuario", "admin"]

    @staticmethod
    def validate_user(uid: int, user_id: str, name: str, role: str) -> None:
        """
        Valida la integridad de los datos de un usuario.

        :param uid: Identificador único del usuario.
        :type uid: int
        :param user_id: Identificador del usuario en el dispositivo.
        :type user_id: str
        :param name: Nombre del usuario.
        :type name: str
        :param role: Rol asignado al usuario.
        :type role: str
        :return: No devuelve ningún valor.
        :rtype: None
        :raises DataValidationError: Si alguno de los datos del usuario no cumple las reglas de validación.
        """
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
        """
        Valida la integridad de un registro de asistencia.

        :param uid: Identificador único opcional del usuario.
        :type uid: int
        :param user_id: Identificador del usuario asociado al registro.
        :type user_id: str
        :param name: Nombre del usuario asociado al registro.
        :type name: str
        :param timestamp: Fecha y hora del registro de asistencia.
        :type timestamp: datetime
        :param status: Estado del registro de asistencia.
        :type status: str
        :return: No devuelve ningún valor.
        :rtype: None
        :raises DataValidationError: Si alguno de los datos de asistencia no cumple las reglas de validación.
        """
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
        """
        Valida que un rango de fechas sea cronológicamente correcto y no termine en el futuro.

        :param start_date: Fecha y hora inicial del rango.
        :type start_date: datetime
        :param end_date: Fecha y hora final del rango.
        :type end_date: datetime
        :return: No devuelve ningún valor.
        :rtype: None
        :raises DataValidationError: Si la fecha inicial es posterior a la final o la fecha final está en el futuro.
        """
        if start_date > end_date:
            raise DataValidationError("Fecha inicial no puede ser mayor que fecha final")
        if end_date > datetime.utcnow():
            raise DataValidationError("Fecha final no puede ser en el futuro")

    @staticmethod
    def validate_pagination(page: int, limit: int) -> None:
        """
        Valida los parámetros utilizados para paginar resultados.

        :param page: Número de página solicitado.
        :type page: int
        :param limit: Cantidad máxima de elementos por página.
        :type limit: int
        :return: No devuelve ningún valor.
        :rtype: None
        :raises DataValidationError: Si la página es menor que uno o el límite está fuera del rango permitido.
        """
        if page < 1:
            raise DataValidationError("page debe ser mayor o igual a 1")
        if limit < 1 or limit > 100:
            raise DataValidationError("limit debe estar entre 1 y 100")