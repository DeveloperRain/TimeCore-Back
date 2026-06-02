"""Middleware de manejo centralizado de errores."""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime
from app.config.logger import get_logger

logger = get_logger("middleware.error_handler")


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware que maneja errores globalmente."""

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except RequestValidationError as e:
            logger.warning(f"Validación fallida en {request.url.path}: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={
                    "status": "error",
                    "data": None,
                    "message": "Datos inválidos en la solicitud",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Validación fallida",
                        "details": str(e)
                    }
                }
            )
        except TimeoutError as e:
            logger.error(f"Timeout en {request.url.path}: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                content={
                    "status": "error",
                    "data": None,
                    "message": "Conexión agotada con el dispositivo",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "error": {
                        "code": "TIMEOUT_ERROR",
                        "message": "Conexión agotada",
                        "details": str(e)
                    }
                }
            )
        except ConnectionError as e:
            logger.error(f"Error de conexión en {request.url.path}: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "error",
                    "data": None,
                    "message": "El dispositivo no está disponible",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "error": {
                        "code": "CONNECTION_ERROR",
                        "message": "Dispositivo no disponible",
                        "details": str(e)
                    }
                }
            )
        except Exception as e:
            logger.error(f"Error no manejado en {request.url.path}: {str(e)}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "status": "error",
                    "data": None,
                    "message": "Error interno del servidor",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "Error no esperado",
                        "details": str(e)
                    }
                }
            )
