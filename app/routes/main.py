# Configuración principal de FastAPI. Registra routers e inicializa tablas de BD.
from fastapi import FastAPI
from app.config.logger import setup_logger
from app.routes.users import router as users_router
from app.routes.device import router as device_router
from app.database.connection import create_tables

logger = setup_logger()
app = FastAPI(
    title="API Reloj Biométrico ZKTeco",
    description="API para gestión de usuarios y asistencia",
    version="1.0.0"
)

# Crear tablas en la base de datos al iniciar
create_tables()

app.include_router(users_router)
app.include_router(device_router)

@app.get("/")
def root():
    logger.info("Health check requested")
    return {
        "status": "online",
        "version": "1.0.0"
    } 