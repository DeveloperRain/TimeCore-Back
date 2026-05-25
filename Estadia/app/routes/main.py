from fastapi import FastAPI
from app.routes.users import router as users_router
from app.routes.device import router as device_router

app = FastAPI()

app.include_router(users_router)
app.include_router(device_router)

@app.get("/")
def root():
    return {
        "status": "online"
    }

