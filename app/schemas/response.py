"""Modelos de respuesta estándar para la API."""
from datetime import datetime
from typing import Generic, TypeVar, Optional, List
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationInfo(BaseModel):
    """Información de paginación."""
    page: int = Field(..., ge=1, description="Página actual")
    limit: int = Field(..., ge=1, description="Items por página")
    total: int = Field(..., ge=0, description="Total de items")
    pages: int = Field(..., ge=0, description="Total de páginas")

    class Config:
        examples = [{
            "page": 1,
            "limit": 20,
            "total": 100,
            "pages": 5
        }]


class ApiResponse(BaseModel, Generic[T]):
    """Respuesta estándar de la API."""
    status: str = Field(..., description="Estado (success, error)")
    data: Optional[T] = Field(None, description="Datos de la respuesta")
    message: Optional[str] = Field(None, description="Mensaje descriptivo")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp ISO8601")
    pagination: Optional[PaginationInfo] = Field(None, description="Info de paginación")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "data": {"id": 1, "name": "Juan"},
                "message": "Operación exitosa",
                "timestamp": "2026-06-02T10:30:00.000Z",
                "pagination": None
            }
        }


class ErrorDetail(BaseModel):
    """Detalle de error."""
    code: str = Field(..., description="Código de error")
    message: str = Field(..., description="Mensaje de error")
    details: Optional[str] = Field(None, description="Detalles adicionales")

    class Config:
        examples = [{
            "code": "VALIDATION_ERROR",
            "message": "Datos inválidos",
            "details": "UID debe ser mayor a 0"
        }]
