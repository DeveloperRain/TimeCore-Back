from fastapi import FastAPI
from app.config.logger import setup_logger
from app.routes.users import router as users_router
from app.routes.device import router as device_router

logger = setup_logger()
app = FastAPI()

app.include_router(users_router)
app.include_router(device_router)

@app.get("/")
def root():
    logger.info("Health check requested")
    return {
        "status": "online"
    }
