from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from io import BytesIO
from app.config.logger import get_logger, log_exception
from app.services.zk_service import ZKService
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

@router.get(
    "/",
    response_model=list[UserResponse],
    summary="Obtener todos los usuarios",
    description="Obtiene la lista de todos los usuarios registrados en el reloj biométrico",
    responses={
        200: {"description": "Lista de usuarios obtenida exitosamente"},
        503: {"description": "El dispositivo no está disponible"}
    }
)
def get_users():
    try:
        usuarios = ZKService.get_all_users()
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
    description="Crea un nuevo usuario en el reloj biométrico con los datos proporcionados",
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
        return result
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Conexión agotada con el dispositivo")
    except ConnectionError:
        raise HTTPException(status_code=503, detail="El dispositivo no está disponible")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear usuario: {str(e)}")

@router.put(
    "/{uid}",
    response_model=dict,
    summary="Actualizar usuario",
    description="Actualiza los datos de un usuario existente. Puede actualizar nombre, ID de usuario o ambos",
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
    "/{uid}",
    summary="Eliminar usuario",
    description="Elimina un usuario del reloj biométrico",
    responses={
        200: {"description": "Usuario eliminado exitosamente"},
        404: {"description": "Usuario no encontrado"},
        503: {"description": "El dispositivo no está disponible"}
    }
)
def delete_user(uid: int):
    try:
        result = ZKService.delete_user(uid)
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
    description="Obtiene todos los registros de asistencia del reloj biométrico",
    responses={
        200: {"description": "Registros de asistencia obtenidos exitosamente"},
        503: {"description": "El dispositivo no está disponible"}
    }
)
def get_attendance():
    try:
        asistencias = ZKService.get_attendance_records()
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
