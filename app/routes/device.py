from fastapi import APIRouter, HTTPException

from app.services.zk_service import ZKService
from app.utils.response import success

router = APIRouter(
    prefix="/device",
    tags=["Dispositivo"]
)

@router.get(
    "/info",
    summary="Obtener información del dispositivo",
    description="Obtiene la información completa y estado del reloj biométrico ZKTeco",
    tags=["Dispositivo"]
)
def get_device_info():
    try:
        device_info = ZKService.get_device_info()
        return success(
            data=device_info,
            message="Información del dispositivo obtenida exitosamente"
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Conexion agotada con el dispositivo")
    except ConnectionError:
        raise HTTPException(status_code=503, detail="El dispositivo no esta disponible")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener informacion del dispositivo: {str(e)}")

