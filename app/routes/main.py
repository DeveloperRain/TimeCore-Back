# Configuración principal de FastAPI. Registra routers e inicializa tablas de BD.
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.config.logger import setup_logger
from app.database.connection import create_tables
from app.middleware.error_handler import ErrorHandlerMiddleware
from app.routes.auth import router as auth_router
from app.routes.branches import router as branches_router
from app.routes.dashboard import router as dashboard_router
from app.routes.db import router as db_router
from app.routes.device import router as device_router
from app.routes.logs import router as logs_router
from app.routes.sync import router as sync_router
from app.routes.usuarios import router as usuarios_router
from app.utils.response import success

logger = setup_logger()

app = FastAPI(
    title="TIMECORE API",
    description="API para gestión de usuarios y asistencia del reloj biométrico ZKTeco/Steren",
    version="1.0.0",
    license_info={
        "name": "MIT"
    }
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ErrorHandlerMiddleware)

# Crear tablas en la base de datos al iniciar
create_tables()

# Routers
app.include_router(auth_router)
app.include_router(usuarios_router)
app.include_router(device_router)
app.include_router(db_router)
app.include_router(sync_router)
app.include_router(dashboard_router)
app.include_router(logs_router)
app.include_router(branches_router)


def custom_openapi():
    """Personalizar documentación OpenAPI."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="TIMECORE API",
        version="1.0.0",
        description="API para gestión de usuarios, asistencia y dispositivo ZKTeco y/o Steren",
        routes=app.routes,
    )

    openapi_schema["info"]["x-logo"] = {
        "url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"
    }

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get(
    "/",
    summary="Health Check",
    description="Verifica que la API está disponible y obtiene información general",
    tags=["General"]
)
def root():
    """Endpoint raíz con información general de la API."""
    logger.info("Health check requested")

    return success(
        data={
            "status": "online",
            "version": "1.0.0",
            "service": "TIMECORE API",
            "timestamp": datetime.utcnow().isoformat(),
            "endpoints": {
                "auth": "/docs#!/Autenticación",
                "usuarios": "/docs#!/Usuarios",
                "dispositivo": "/docs#!/Dispositivo",
                "documentation": "/docs",
            },
        },
        message="API disponible y funcionando correctamente"
    )