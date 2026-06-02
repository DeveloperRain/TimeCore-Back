from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from io import BytesIO
from datetime import datetime, time
from app.config.logger import get_logger, log_exception
from app.services.zk_service import ZKService
from app.services.db_service import DBService
from app.services.excel_service import build_attendance_excel
from app.schemas.user_schema import (
    UserCreate, UserUpdate, UserResponse, AttendanceRecord, ErrorResponse
)

logger = get_logger("routes.users")
router = APIRouter(
    prefix="/users",
    tags=["users"],
    responses={503: {"model": ErrorResponse, "description": "Servicio no disponible"}}
)

DATE_FORMATS = (
    "%d-%m-%Y",
    "%d/%m/%Y",
)


def parse_report_date(value: str) -> datetime.date:
    value = value.strip()
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue

    raise HTTPException(
        status_code=400,
        detail="Formato de fecha invalido. Usa DD-MM-YYYY o DD/MM/YYYY",
    )

@router.get(
    "/",
    response_model=list[UserResponse],
    summary="Obtener todos los usuarios",
    description="Obtiene la lista de todos los usuarios registrados en el reloj biométrico y sincroniza con BD",
    responses={
        200: {"description": "Lista de usuarios obtenida exitosamente"},
        503: {"description": "El dispositivo no está disponible"}
    }
)
def get_users():
    try:
        usuarios = ZKService.get_all_users()
        # Sincronizar con BD
        for user in usuarios:
            try:
                DBService.save_user(
                    uid=user["uid"],
                    user_id=user["user_id"],
                    name=user["name"],
                    role=user["role"]
                )
            except Exception as e:
                logger.warning(f"Error al sincronizar usuario {user.get('uid')} en BD: {str(e)}")

        return usuarios
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Conexión agotada con el dispositivo")
    except ConnectionError:
        raise HTTPException(status_code=503, detail="El dispositivo no está disponible")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener usuarios: {str(e)}")

@router.post(
    "/",
    response_model=dict,
    summary="Crear nuevo usuario",
    description="Crea un nuevo usuario en el reloj biométrico y sincroniza en BD",
    responses={
        200: {"description": "Usuario creado exitosamente"},
        400: {"description": "Datos inválidos"},
        503: {"description": "El dispositivo no está disponible"}
    }
)
def create_user(user: UserCreate):
    try:
        result = ZKService.create_user(
            uid=user.uid,
            user_id=user.user_id,
            name=user.name,
            role=user.role
        )
        # Sincronizar con BD
        try:
            DBService.save_user(
                uid=user.uid,
                user_id=user.user_id,
                name=user.name,
                role=user.role
            )
        except Exception as e:
            logger.warning(f"Error al sincronizar usuario {user.uid} en BD: {str(e)}")

        return result
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Conexión agotada con el dispositivo")
    except ConnectionError:
        raise HTTPException(status_code=503, detail="El dispositivo no está disponible")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear usuario: {str(e)}")

@router.put(
    "/{uid:int}",
    response_model=dict,
    summary="Actualizar usuario",
    description="Actualiza los datos de un usuario en el reloj y sincroniza en BD",
    responses={
        200: {"description": "Usuario actualizado exitosamente"},
        400: {"description": "Datos inválidos o usuario no encontrado"},
        503: {"description": "El dispositivo no está disponible"}
    }
)
def update_user(uid: int, user: UserUpdate):
    try:
        if not user.uid and not user.user_id and not user.name and not user.role:
            raise HTTPException(
                status_code=400,
                detail="Al menos un campo debe ser proporcionado (uid, user_id, name o role)"
            )

        result = ZKService.update_user(
            uid=uid,
            user_id=user.user_id,
            name=user.name,
            role=user.role
        )
        # Sincronizar con BD
        try:
            DBService.save_user(
                uid=uid,
                user_id=user.user_id or result.get("user_id"),
                name=user.name or result.get("name"),
                role=user.role or result.get("role")
            )
        except Exception as e:
            logger.warning(f"Error al sincronizar usuario {uid} en BD: {str(e)}")

        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Conexión agotada con el dispositivo")
    except ConnectionError:
        raise HTTPException(status_code=503, detail="El dispositivo no está disponible")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al actualizar usuario: {str(e)}")

@router.delete(
    "/{uid:int}",
    summary="Eliminar usuario",
    description="Elimina un usuario del reloj biométrico y marca como eliminado en BD",
    responses={
        200: {"description": "Usuario eliminado exitosamente"},
        404: {"description": "Usuario no encontrado"},
        503: {"description": "El dispositivo no está disponible"}
    }
)
def delete_user(uid: int):
    try:
        result = ZKService.delete_user(uid)
        # Sincronizar con BD
        try:
            DBService.delete_user(uid)
        except Exception as e:
            logger.warning(f"Error al eliminar usuario {uid} en BD: {str(e)}")

        return result
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Conexión agotada con el dispositivo")
    except ConnectionError:
        raise HTTPException(status_code=503, detail="El dispositivo no está disponible")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar usuario: {str(e)}")

@router.get(
    "/attendance",
    response_model=list[AttendanceRecord],
    summary="Obtener registros de asistencia",
    description="Obtiene todos los registros de asistencia del reloj biométrico y sincroniza en BD",
    responses={
        200: {"description": "Registros de asistencia obtenidos exitosamente"},
        503: {"description": "El dispositivo no está disponible"}
    }
)
def get_attendance():
    try:
        asistencias = ZKService.get_attendance_records()

        # Sincronizar con BD
        try:
            records_to_save = []
            for att in asistencias:
                att_dict = att.__dict__ if hasattr(att, '__dict__') else att
                records_to_save.append(att_dict)

            if records_to_save:
                DBService.save_bulk_attendance(records_to_save)
        except Exception as e:
            logger.warning(f"Error al sincronizar asistencias en BD: {str(e)}")

        return asistencias
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Conexión agotada con el dispositivo")
    except ConnectionError:
        raise HTTPException(status_code=503, detail="El dispositivo no está disponible")
    except Exception as e:
        log_exception(logger, e, "Error al obtener asistencias")
        raise HTTPException(status_code=500, detail=f"Error al obtener asistencias: {str(e)}")


@router.get(
    "/attendance/download",
    summary="Descargar registros de asistencia en Excel",
    description="Descarga registros de asistencia del reloj en formato Excel",
    responses={
        200: {"description": "Archivo Excel descargado"},
        503: {"description": "El dispositivo no está disponible"}
    }
)
def download_attendance_excel():
    try:
        asistencias = ZKService.get_attendance_records()
        records_dict = [record.__dict__ if hasattr(record, '__dict__') else record for record in asistencias]
        excel_bytes = build_attendance_excel(records_dict)

        return StreamingResponse(
            BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=asistencias.xlsx"}
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Conexión agotada con el dispositivo")
    except ConnectionError:
        raise HTTPException(status_code=503, detail="El dispositivo no está disponible")
    except Exception as e:
        log_exception(logger, e, "Error al descargar asistencias")
        raise HTTPException(status_code=500, detail=f"Error al descargar asistencias: {str(e)}")


@router.get(
    "/attendance/report",
    summary="Obtener reporte de asistencia por fecha",
    description="Obtiene registros de asistencia de la BD filtrados por rango de fechas",
    responses={
        200: {"description": "Registros obtenidos"},
        400: {"description": "Fechas inválidas"}
    }
)
def get_attendance_report(
    start_date: str = Query(..., description="Fecha inicial. Formato: DD-MM-YYYY o DD/MM/YYYY"),
    end_date: str = Query(..., description="Fecha final. Formato: DD-MM-YYYY o DD/MM/YYYY"),
):
    try:
        parsed_start_date = parse_report_date(start_date)
        parsed_end_date = parse_report_date(end_date)

        if parsed_start_date > parsed_end_date:
            raise HTTPException(status_code=400, detail="La fecha inicial no puede ser mayor que la fecha final")

        start = datetime.combine(parsed_start_date, time.min)
        end = datetime.combine(parsed_end_date, time.max)

        records = DBService.get_attendance_by_date_range(start, end)
        return [record.to_dict() for record in records]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al obtener reporte: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener reporte: {str(e)}")
