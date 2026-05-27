from fastapi import APIRouter, HTTPException

from app.services.zk_service import ZKService

router = APIRouter(
    prefix="/device",
    tags=["device"]
)

@router.get(
    "/info",
    summary="Obtener informacion del dispositivo",
    description="Obtiene la informacion disponible del reloj biometrico"
)
def get_device_info():
    try:
        return ZKService.get_device_info()
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Conexion agotada con el dispositivo")
    except ConnectionError:
        raise HTTPException(status_code=503, detail="El dispositivo no esta disponible")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener informacion del dispositivo: {str(e)}")
