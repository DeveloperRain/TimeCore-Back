# Configuración principal de FastAPI. Registra routers e inicializa tablas de BD.
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.config.logger import setup_logger
from app.database.connection import create_tables
from app.middleware.error_handler import ErrorHandlerMiddleware, register_exception_handlers
from app.services.automatic_sync_service import automatic_sync_loop
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Inicia la tarea de sincronización automática y la detiene al cerrar la API.

    :param app: Instancia principal de la aplicación FastAPI.
    :type app: FastAPI
    :return: Contexto asíncrono que controla el ciclo de vida de la aplicación.
    :rtype: AsyncIterator[None]
    :raises Exception: Si ocurre un error no controlado durante el inicio o cierre de la aplicación.
    """
    sync_task = asyncio.create_task(automatic_sync_loop())

    try:
        yield
    finally:
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="TIMECORE API",
    description="API para gestión de usuarios y asistencia del reloj biométrico ZKTeco/Steren",
    version="1.0.0",
    lifespan=lifespan,
    license_info={
        "name": "MIT"
    }
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=(
        r"^http://("
        r"localhost"
        r"|127\.0\.0\.1"
        r"|192\.168\.\d{1,3}\.\d{1,3}"      # Redes LAN locales (cualquier sucursal)
        r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"   # Otro rango LAN privado común
        r"|25\.\d{1,3}\.\d{1,3}\.\d{1,3}"   # Rango de IPs virtuales de Hamachi
        r"):\d+$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ErrorHandlerMiddleware)
register_exception_handlers(app)

# Crear tablas en la base de datos al iniciar
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Inicializa las tablas de la base de datos y controla la sincronización automática.

    :param app: Instancia principal de la aplicación FastAPI.
    :type app: FastAPI
    :return: Contexto asíncrono que controla el ciclo de vida de la aplicación.
    :rtype: AsyncIterator[None]
    :raises Exception: Si ocurre un error no controlado durante la inicialización o cierre de los recursos.
    """

    create_tables()
    sync_task = asyncio.create_task(automatic_sync_loop())

    try:
        yield
    finally:
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            pass

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
    """
    Genera y almacena el esquema OpenAPI personalizado de la aplicación.

    :return: Esquema OpenAPI configurado para la API.
    :rtype: dict
    """
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
    """
    Verifica la disponibilidad de la API y devuelve su información general.

    :return: Respuesta con el estado, versión, servicio, fecha y endpoints de la API.
    :rtype: dict
    """
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