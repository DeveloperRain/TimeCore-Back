"""Manejo centralizado y consistente de errores HTTP."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config.logger import get_logger
from app.exceptions import TimeCoreError

logger = get_logger("middleware.error_handler")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def _payload(
    request: Request,
    *,
    message: str,
    code: str,
    details: Any = None,
) -> dict[str, Any]:
    return {
        "status": "error",
        "data": None,
        "message": message,
        "timestamp": _timestamp(),
        "request_id": _request_id(request),
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
    }


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Añade un identificador a cada petición y captura fallos no previstos."""

    async def dispatch(self, request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request.state.request_id
            return response
        except Exception as exc:  # última barrera; los errores conocidos usan handlers
            logger.exception(
                "Error no controlado [%s] %s %s",
                request.state.request_id,
                request.method,
                request.url.path,
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=_payload(
                    request,
                    message="Ocurrió un error interno. Intenta nuevamente.",
                    code="INTERNAL_ERROR",
                ),
                headers={"X-Request-ID": request.state.request_id},
            )


def register_exception_handlers(app: FastAPI) -> None:
    """Registra todos los manejadores de excepción de TimeCore."""

    @app.exception_handler(TimeCoreError)
    async def timecore_error_handler(request: Request, exc: TimeCoreError):
        log = logger.error if exc.status_code >= 500 else logger.warning
        log(
            "%s [%s] %s %s: %s",
            exc.code,
            _request_id(request),
            request.method,
            request.url.path,
            exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(
                request,
                message=exc.message,
                code=exc.code,
                details=exc.details,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        errors = [
            {
                "field": ".".join(str(item) for item in error.get("loc", [])[1:]),
                "message": error.get("msg", "Valor inválido"),
                "type": error.get("type", "validation_error"),
            }
            for error in exc.errors()
        ]
        logger.warning(
            "VALIDATION_ERROR [%s] %s %s: %s",
            _request_id(request),
            request.method,
            request.url.path,
            errors,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_payload(
                request,
                message="Revisa los datos enviados",
                code="VALIDATION_ERROR",
                details=errors,
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            message = str(detail.get("message") or detail.get("detail") or "Solicitud inválida")
            code = str(detail.get("code") or f"HTTP_{exc.status_code}")
            details = detail.get("details")
        else:
            message = str(detail)
            code = f"HTTP_{exc.status_code}"
            details = None

        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(request, message=message, code=code, details=details),
            headers=exc.headers,
        )

    @app.exception_handler(TimeoutError)
    async def timeout_error_handler(request: Request, exc: TimeoutError):
        logger.error("TIMEOUT [%s] %s", _request_id(request), exc)
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content=_payload(
                request,
                message="El reloj tardó demasiado en responder",
                code="DEVICE_TIMEOUT",
            ),
        )

    @app.exception_handler(ConnectionError)
    async def connection_error_handler(request: Request, exc: ConnectionError):
        logger.error("CONNECTION_ERROR [%s] %s", _request_id(request), exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=_payload(
                request,
                message="No fue posible comunicarse con el reloj",
                code="DEVICE_UNAVAILABLE",
            ),
        )
