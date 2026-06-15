from fastapi import APIRouter, HTTPException
from app.services.zk_service import ZKService
from app.services.db_service import DBService
from app.utils.response import success
from app.config.logger import get_logger, log_exception

logger = get_logger("routes.sync")

router = APIRouter(
    prefix="/sync",
    tags=["Sincronización"]
)


@router.post("/users", summary="Sincronizar usuarios del reloj a PostgreSQL")
def sync_users():
    try:
        usuarios = ZKService.get_all_users()

        count = 0

        for user in usuarios:
            DBService.save_user(
                uid=user["uid"],
                user_id=user["user_id"],
                name=user["name"],
                role=user["role"]
            )
            count += 1

        return success(
            data={"synced": count},
            message=f"Se sincronizaron {count} usuarios correctamente"
        )

    except Exception as e:
        log_exception(logger, e, "Error al sincronizar usuarios")
        raise HTTPException(
            status_code=500,
            detail=f"Error al sincronizar usuarios: {str(e)}"
        )


@router.post("/attendance", summary="Sincronizar asistencias del reloj a PostgreSQL")
def sync_attendance():
    try:
        asistencias = ZKService.get_attendance_records()

        records_to_save = []

        for att in asistencias:
            att_dict = att.__dict__ if hasattr(att, "__dict__") else att
            records_to_save.append(att_dict)

        count = DBService.save_bulk_attendance(records_to_save)

        return success(
            data={"synced": count},
            message=f"Se sincronizaron {count} asistencias correctamente"
        )

    except Exception as e:
        log_exception(logger, e, "Error al sincronizar asistencias")
        raise HTTPException(
            status_code=500,
            detail=f"Error al sincronizar asistencias: {str(e)}"
        )


@router.post("/all", summary="Sincronizar usuarios y asistencias")
def sync_all():
    try:
        usuarios = ZKService.get_all_users()

        users_count = 0

        for user in usuarios:
            DBService.save_user(
                uid=user["uid"],
                user_id=user["user_id"],
                name=user["name"],
                role=user["role"]
            )
            users_count += 1

        asistencias = ZKService.get_attendance_records()

        records_to_save = []

        for att in asistencias:
            att_dict = att.__dict__ if hasattr(att, "__dict__") else att
            records_to_save.append(att_dict)

        attendance_count = DBService.save_bulk_attendance(records_to_save)

        return success(
            data={
                "users_synced": users_count,
                "attendance_synced": attendance_count
            },
            message="Sincronización completa realizada correctamente"
        )

    except Exception as e:
        log_exception(logger, e, "Error en sincronización completa")
        raise HTTPException(
            status_code=500,
            detail=f"Error en sincronización completa: {str(e)}"
        )