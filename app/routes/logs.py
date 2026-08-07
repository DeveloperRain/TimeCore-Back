from fastapi import APIRouter, Query
from app.services.db_service import DBService
from app.utils.response import success

router = APIRouter(
    prefix="/logs",
    tags=["Logs"]
)


@router.get("/", summary="Obtener logs de auditoría")
def get_logs(limit: int = Query(100, ge=1, le=500)):
    """
    Obtiene una cantidad limitada de logs de auditoría desde la base de datos.

    :param limit: Cantidad máxima de logs que se deben obtener.
    :type limit: int
    :return: Respuesta con los logs de auditoría encontrados.
    :rtype: dict
    """
    logs = DBService.get_logs(limit=limit)

    data = [
        {
            "id": log.id,
            "accion": log.accion,
            "detalle": log.detalle,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]

    return success(
        data=data,
        message=f"Se obtuvieron {len(data)} logs de auditoría"
    )