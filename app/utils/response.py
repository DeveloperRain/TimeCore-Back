"""Helpers para respuestas API."""
from datetime import datetime
from typing import Optional, List, TypeVar, Generic
from app.schemas.response import ApiResponse, PaginationInfo, ErrorDetail

T = TypeVar("T")


class ApiResponseBuilder:
    """Helper para construir respuestas API estándar."""

    @staticmethod
    def success(data: Optional[T] = None, message: str = "Operación exitosa") -> dict:
        """Construir respuesta exitosa."""
        return {
            "status": "success",
            "data": data,
            "message": message,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    @staticmethod
    def error(message: str, code: str = "ERROR", details: Optional[str] = None) -> dict:
        """Construir respuesta de error."""
        return {
            "status": "error",
            "data": None,
            "message": message,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error": {
                "code": code,
                "message": message,
                "details": details
            }
        }

    @staticmethod
    def paginated(
        data: List[T],
        page: int,
        limit: int,
        total: int,
        message: str = "Datos obtenidos"
    ) -> dict:
        """Construir respuesta paginada."""
        pages = (total + limit - 1) // limit
        return {
            "status": "success",
            "data": data,
            "message": message,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": pages
            }
        }


# Aliases convenientes
def success(data=None, message="Operación exitosa"):
    """Respuesta exitosa."""
    return ApiResponseBuilder.success(data, message)


def error(message, code="ERROR", details=None):
    """Respuesta de error."""
    return ApiResponseBuilder.error(message, code, details)


def paginated(data, page, limit, total, message="Datos obtenidos"):
    """Respuesta paginada."""
    return ApiResponseBuilder.paginated(data, page, limit, total, message)

