from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from io import BytesIO
from datetime import datetime, time, timedelta
from typing import Optional

from app.config.logger import get_logger, log_exception
from app.services.zk_service import ZKService
from app.services.db_service import DBService
from app.services.excel_service import build_attendance_excel
from app.exceptions import DataValidationError, DuplicateUserError
from app.schemas.user_schema import (
    UserCreate, UserUpdate, ErrorResponse
)
from app.utils.response import success, paginated

logger = get_logger("routes.usuarios")

router = APIRouter(
    prefix="/users",
    responses={503: {"model": ErrorResponse, "description": "Servicio no disponible"}}
)

DATE_FORMATS = (
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%Y-%m-%d",
)


def parse_report_date(value: str):
    value = value.strip()

    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue

    raise HTTPException(
        status_code=400,
        detail="Formato de fecha invalido. Usa YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY",
    )


@router.get(
    "/",
    summary="Obtener todos los usuarios",
    description="Obtiene la lista paginada de usuarios registrados en el reloj biométrico y sincroniza con BD",
    tags=["Usuarios"]
)
def get_users(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(20, ge=1, le=100, description="Items por página")
):
    try:
        from app.services.validators import DataValidator

        DataValidator.validate_pagination(page, limit)

        usuarios = ZKService.get_all_users()

        for user in usuarios:
            try:
                DBService.save_user(
                    uid=user["uid"],
                    user_id=user["user_id"],
                    name=user["name"],
                    role=user["role"]
                )
            except DataValidationError as e:
                logger.warning(f"Usuario inválido descartado del reloj: {e}")
            except Exception as e:
                logger.warning(f"Error al sincronizar usuario {user.get('uid')} en BD: {str(e)}")

        total = len(usuarios)
        start = (page - 1) * limit
        end = start + limit
        usuarios_paginados = usuarios[start:end]

        return paginated(
            data=usuarios_paginados,
            page=page,
            limit=limit,
            total=total,
            message=f"Se obtuvieron {len(usuarios_paginados)} usuarios"
        )

    except DataValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Conexión agotada con el dispositivo")
    except ConnectionError:
        raise HTTPException(status_code=503, detail="El dispositivo no está disponible")
    except Exception as e:
        logger.error(f"Error al obtener usuarios: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener usuarios: {str(e)}")


@router.post(
    "/",
    summary="Crear nuevo usuario",
    description="Crea un nuevo usuario en el reloj biométrico y sincroniza en BD",
    tags=["Usuarios"]
)
def create_user(user: UserCreate):
    try:
        result = ZKService.create_user(
            uid=user.uid,
            user_id=user.user_id,
            name=user.name,
            role=user.role
        )

        try:
            DBService.save_user(
                uid=user.uid,
                user_id=user.user_id,
                name=user.name,
                role=user.role
            )
        except Exception as e:
            logger.warning(f"Error al sincronizar usuario {user.uid} en BD: {str(e)}")

        return success(
            data=result["user"],
            message=result["message"]
        )

    except DuplicateUserError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Conexión agotada con el dispositivo")
    except ConnectionError:
        raise HTTPException(status_code=503, detail="El dispositivo no está disponible")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear usuario: {str(e)}")


@router.put(
    "/{uid:int}",
    summary="Actualizar usuario",
    description="Actualiza los datos de un usuario en el reloj y sincroniza en BD",
    tags=["Usuarios"]
)
def update_user(uid: int, user: UserUpdate):
    try:
        if not user.user_id and not user.name and not user.role:
            raise HTTPException(
                status_code=400,
                detail="Al menos un campo debe ser proporcionado (user_id, name o role)"
            )

        result = ZKService.update_user(
            uid=uid,
            user_id=user.user_id,
            name=user.name,
            role=user.role
        )

        try:
            DBService.save_user(
                uid=uid,
                user_id=user.user_id or result.get("user", {}).get("user_id"),
                name=user.name or result.get("user", {}).get("name"),
                role=user.role or result.get("user", {}).get("role")
            )
        except Exception as e:
            logger.warning(f"Error al sincronizar usuario {uid} en BD: {str(e)}")

        return success(
            data=result.get("user"),
            message=result.get("message")
        )

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
    tags=["Usuarios"]
)
def delete_user(uid: int):
    try:
        result = ZKService.delete_user(uid)

        try:
            DBService.delete_user(uid)
        except Exception as e:
            logger.warning(f"Error al eliminar usuario {uid} en BD: {str(e)}")

        return success(
            data={"uid": uid},
            message=result["message"]
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Conexión agotada con el dispositivo")
    except ConnectionError:
        raise HTTPException(status_code=503, detail="El dispositivo no está disponible")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar usuario: {str(e)}")


@router.get(
    "/attendance",
    summary="Obtener registros de asistencia",
    description="Obtiene los registros paginados de asistencia del reloj biométrico y sincroniza en BD",
    tags=["Asistencia"]
)
def get_attendance(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(20, ge=1, le=100, description="Items por página")
):
    try:
        from app.services.validators import DataValidator

        DataValidator.validate_pagination(page, limit)

        asistencias = ZKService.get_attendance_records()

        try:
            records_to_save = []
            for att in asistencias:
                att_dict = att.__dict__ if hasattr(att, "__dict__") else att
                records_to_save.append(att_dict)

            if records_to_save:
                DBService.save_bulk_attendance(records_to_save)
        except Exception as e:
            logger.warning(f"Error al sincronizar asistencias en BD: {str(e)}")

        total = len(asistencias)
        start = (page - 1) * limit
        end = start + limit
        asistencias_paginadas = asistencias[start:end]

        return paginated(
            data=asistencias_paginadas,
            page=page,
            limit=limit,
            total=total,
            message=f"Se obtuvieron {len(asistencias_paginadas)} registros de asistencia"
        )

    except DataValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
    description="Descarga registros de asistencia en Excel con filtros por hoy, semana, rango de fechas o todas",
    tags=["Asistencia"]
)
def download_attendance_excel(
    modo: str = Query("todas", description="Opciones: hoy, semana o todas"),
    start_date: Optional[str] = Query(None, description="Fecha inicial: YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY"),
    end_date: Optional[str] = Query(None, description="Fecha final: YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY"),
):
    try:
        from app.services.validators import DataValidator

        modo = modo.lower().strip()

        if modo not in ("hoy", "semana", "todas"):
            raise HTTPException(
                status_code=400,
                detail="Modo invalido. Usa: hoy, semana o todas"
            )

        if (start_date and not end_date) or (end_date and not start_date):
            raise HTTPException(
                status_code=400,
                detail="Debes enviar start_date y end_date juntos"
            )

        start = None
        end = None
        filename = "asistencias_todas.xlsx"

        today = datetime.now().date()

        if start_date and end_date:
            parsed_start_date = parse_report_date(start_date)
            parsed_end_date = parse_report_date(end_date)

            start = datetime.combine(parsed_start_date, time.min)
            end = datetime.combine(parsed_end_date, time.max)

            DataValidator.validate_date_range(start, end)

            filename = (
                f"asistencias_{start_date.replace('/', '-')}"
                f"_a_{end_date.replace('/', '-')}.xlsx"
            )

        elif modo == "hoy":
            start = datetime.combine(today, time.min)
            end = datetime.combine(today, time.max)

            filename = f"asistencias_hoy_{today}.xlsx"

        elif modo == "semana":
            start_of_week = today - timedelta(days=today.weekday())
            end_of_week = start_of_week + timedelta(days=6)

            start = datetime.combine(start_of_week, time.min)
            end = datetime.combine(end_of_week, time.max)

            filename = f"asistencias_semana_{start_of_week}_a_{end_of_week}.xlsx"

        if start and end:
            records = DBService.get_attendance_by_date_range(start, end)
            records_dict = [record.to_dict() for record in records]
        else:
            asistencias = ZKService.get_attendance_records()
            records_dict = [
                record.__dict__ if hasattr(record, "__dict__") else record
                for record in asistencias
            ]

        excel_bytes = build_attendance_excel(records_dict)

        return StreamingResponse(
            BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException:
        raise
    except DataValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Conexión agotada con el dispositivo")
    except ConnectionError:
        raise HTTPException(status_code=503, detail="El dispositivo no está disponible")
    except Exception as e:
        log_exception(logger, e, "Error al descargar asistencias")
        raise HTTPException(status_code=500, detail=f"Error al descargar asistencias: {str(e)}")


@router.get(
    "/attendance/dates",
    summary="Obtener fechas con registros de asistencia",
    description="Obtiene la lista de días en los que hubo registros de asistencia y el total por día",
    tags=["Asistencia"]
)
def get_attendance_dates():
    try:
        dates_summary = DBService.get_attendance_dates_summary()

        return success(
            data=dates_summary,
            message=f"Se obtuvieron {len(dates_summary)} fechas con registros"
        )

    except Exception as e:
        logger.error(f"Error al obtener fechas con asistencia: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener fechas con asistencia: {str(e)}")


@router.get(
    "/attendance/report",
    summary="Obtener reporte de asistencia por fecha",
    description="Obtiene registros de asistencia de la BD filtrados por rango de fechas",
    tags=["Asistencia"]
)
def get_attendance_report(
    start_date: str = Query(..., description="Fecha inicial. Formato: YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY"),
    end_date: str = Query(..., description="Fecha final. Formato: YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY"),
):
    try:
        from app.services.validators import DataValidator

        parsed_start_date = parse_report_date(start_date)
        parsed_end_date = parse_report_date(end_date)

        start = datetime.combine(parsed_start_date, time.min)
        end = datetime.combine(parsed_end_date, time.max)

        DataValidator.validate_date_range(start, end)

        records = DBService.get_attendance_by_date_range(start, end)
        records_dict = [record.to_dict() for record in records]

        return success(
            data=records_dict,
            message=f"Se obtuvieron {len(records_dict)} registros del {start_date} al {end_date}"
        )

    except HTTPException:
        raise
    except DataValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al obtener reporte: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener reporte: {str(e)}")


@router.get(
    "/attendance/report/download",
    summary="Descargar registros de asistencia por fechas en Excel",
    description="Descarga registros de asistencia filtrados por rango de fechas en formato Excel",
    tags=["Asistencia"]
)
def download_attendance_report(
    start_date: str = Query(..., description="Fecha inicial. Formato: YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY"),
    end_date: str = Query(..., description="Fecha final. Formato: YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY"),
):
    try:
        from app.services.validators import DataValidator

        parsed_start_date = parse_report_date(start_date)
        parsed_end_date = parse_report_date(end_date)

        start = datetime.combine(parsed_start_date, time.min)
        end = datetime.combine(parsed_end_date, time.max)

        DataValidator.validate_date_range(start, end)

        records = DBService.get_attendance_by_date_range(start, end)
        records_dict = [record.to_dict() for record in records]

        excel_bytes = build_attendance_excel(records_dict)

        filename = (
            f"asistencias_{start_date.replace('/', '-')}"
            f"_a_{end_date.replace('/', '-')}.xlsx"
        )

        return StreamingResponse(
            BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException:
        raise
    except DataValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al descargar reporte: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al descargar reporte: {str(e)}")