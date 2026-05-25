from fastapi import APIRouter, HTTPException

router = APIRouter(
    prefix="/device",
    tags=["device"]
)

@router.get(
    "/info",
    summary="Obtener información del dispositivo",
    description="Obtiene la información del reloj biométrico"
)
def get_device_info():
    return {
        "message": "Funcionalidad de información del dispositivo no disponible en esta versión de la librería ZK",
        "status": "not_supported"
    }

