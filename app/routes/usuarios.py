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
from app.schemas.user_schema import UserCreate, UserUpdate, UserCopyToDevice, ErrorResponse
from app.utils.response import success, paginated

logger = get_logger("routes.usuarios")

router = APIRouter(
    prefix="/users",
    responses={
        503: {
            "model": ErrorResponse,
            "description": "Servicio no disponible",
        }
    },
)

DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
)


def parse_report_date(value: str):
    """
    Convierte una fecha de texto utilizando los formatos admitidos para los reportes.

    :param value: Fecha que se debe interpretar.
    :type value: str
    :return: Fecha convertida a un objeto de fecha.
    :rtype: datetime.date
    :raises HTTPException: Si el valor no coincide con ninguno de los formatos admitidos.
    """
    value = value.strip()

    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue

    raise HTTPException(
        status_code=400,
        detail="Formato de fecha inválido. Usa YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY",
    )


def get_safe_end_datetime(parsed_end_date):
    """
    Obtiene la fecha y hora final segura para un rango de consulta.

    Si la fecha indicada corresponde al día actual, utiliza la fecha y hora
    presentes. En caso contrario, utiliza el último instante del día indicado.

    :param parsed_end_date: Fecha final previamente interpretada.
    :type parsed_end_date: datetime.date
    :return: Fecha y hora que se utilizarán como límite final.
    :rtype: datetime
    """
    today = datetime.now().date()

    if parsed_end_date == today:
        return datetime.now()

    return datetime.combine(parsed_end_date, time.max)


def get_target_device(
    branch_id: Optional[int] = None,
    device_id: Optional[int] = None,
):
    """
    Obtiene el dispositivo solicitado o el primer dispositivo activo disponible.

    :param branch_id: Identificador opcional de la sucursal utilizada para filtrar dispositivos.
    :type branch_id: int or None
    :param device_id: Identificador opcional del dispositivo solicitado.
    :type device_id: int or None
    :return: Dispositivo activo encontrado o ``None`` si no existe uno válido.
    :rtype: object or None
    """
    if device_id is not None:
        device = DBService.get_device_by_id(device_id)

        if not device:
            return None

        if branch_id is not None and getattr(device, "branch_id", None) != branch_id:
            return None

        return device if bool(getattr(device, "is_active", True)) else None

    devices = (
        DBService.get_devices_by_branch(branch_id)
        if branch_id is not None
        else DBService.get_all_devices()
    )

    for device in devices:
        if bool(getattr(device, "is_active", True)):
            return device

    return None


@router.get(
    "/",
    summary="Obtener todos los usuarios",
    description="Obtiene la lista paginada de usuarios registrados en el reloj biométrico y sincroniza con BD",
    tags=["Usuarios"],
)
def get_users(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(
        1000,
        ge=1,
        le=1000,
        description="Empleados por página. Máximo 1000 contando todas las sucursales.",
    ),
):
    """
    Obtiene usuarios del reloj biométrico, los sincroniza con la base de datos y pagina el resultado.

    :param page: Número de página solicitado.
    :type page: int
    :param limit: Cantidad máxima de usuarios incluidos por página.
    :type limit: int
    :return: Respuesta paginada con los usuarios obtenidos.
    :rtype: dict
    :raises HTTPException: Si los datos son inválidos, el dispositivo no está disponible o ocurre un error durante la consulta.
    """
    try:
        usuarios = ZKService.get_all_users()

        for user in usuarios:
            try:
                DBService.save_user(
                    uid=user["uid"],
                    user_id=user["user_id"],
                    name=user["name"],
                    role=user["role"],
                )
            except DataValidationError as e:
                logger.warning(f"Usuario inválido descartado del reloj: {e}")
            except Exception as e:
                logger.warning(
                    f"Error al sincronizar usuario {user.get('uid')} en BD: {str(e)}"
                )

        total = len(usuarios)
        start = (page - 1) * limit
        end = start + limit
        usuarios_paginados = usuarios[start:end]

        return paginated(
            data=usuarios_paginados,
            page=page,
            limit=limit,
            total=total,
            message=f"Se obtuvieron {len(usuarios_paginados)} usuarios",
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
    
def get_users(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(100, ge=1, le=1000, description="Items por página"),
):
    """
    Obtiene usuarios del reloj biométrico, valida la paginación y sincroniza los registros con la base de datos.

    :param page: Número de página solicitado.
    :type page: int
    :param limit: Cantidad máxima de elementos incluidos por página.
    :type limit: int
    :return: Respuesta paginada con los usuarios obtenidos.
    :rtype: dict
    :raises HTTPException: Si la paginación es inválida, el dispositivo no está disponible o ocurre un error durante la consulta.
    """
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
                    role=user["role"],
                )
            except DataValidationError as e:
                logger.warning(f"Usuario inválido descartado del reloj: {e}")
            except Exception as e:
                logger.warning(
                    f"Error al sincronizar usuario {user.get('uid')} en BD: {str(e)}"
                )

        total = len(usuarios)
        start = (page - 1) * limit
        end = start + limit
        usuarios_paginados = usuarios[start:end]

        return paginated(
            data=usuarios_paginados,
            page=page,
            limit=limit,
            total=total,
            message=f"Se obtuvieron {len(usuarios_paginados)} usuarios",
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


@router.get(
    "/device/{device_id:int}/next-uid",
    summary="Obtener siguiente UID disponible del reloj",
    tags=["Usuarios"],
)
def get_next_uid_for_device(device_id: int):
    """
    Obtiene el siguiente UID disponible para un dispositivo registrado.

    :param device_id: Identificador del dispositivo que se debe consultar.
    :type device_id: int
    :return: Respuesta con el dispositivo y el siguiente UID disponible.
    :rtype: dict
    :raises HTTPException: Si el dispositivo no existe, está inactivo o no se puede calcular el UID.
    """
    device = DBService.get_device_by_id(device_id)

    if not device:
        raise HTTPException(status_code=404, detail="Reloj no encontrado")

    if not bool(getattr(device, "is_active", True)):
        raise HTTPException(status_code=409, detail="El reloj está inactivo")

    try:
        next_uid = DBService.get_next_uid_for_device(device.id)

        return success(
            data={
                "device_id": device.id,
                "device_name": device.name,
                "next_uid": next_uid,
            },
            message="Siguiente UID calculada correctamente",
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Conexión agotada con el dispositivo")
    except ConnectionError:
        raise HTTPException(status_code=503, detail="El dispositivo no está disponible")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error calculando la siguiente UID")
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo calcular la siguiente UID: {str(e)}",
        )


@router.post(
    "/by-id/{source_user_id:int}/copy-to-device",
    summary="Crear otra asignacion del empleado en otro reloj",
    description=(
        "Crea al empleado fisicamente en el reloj destino y genera una nueva "
        "fila independiente en PostgreSQL. La asignacion original y sus "
        "asistencias historicas permanecen intactas."
    ),
    tags=["Usuarios"],
)
def copy_user_to_device(
    source_user_id: int,
    payload: UserCopyToDevice,
):
    """
    Crea una asignación independiente de un empleado en otro dispositivo.

    :param source_user_id: Identificador interno del empleado de origen.
    :type source_user_id: int
    :param payload: Datos del dispositivo de destino.
    :type payload: UserCopyToDevice
    :return: Respuesta con la nueva asignación y los datos del dispositivo de destino.
    :rtype: dict
    :raises HTTPException: Si el empleado o el dispositivo no existen, el destino no es válido o falla la creación de la asignación.
    """
    source_user = DBService.get_user_by_id(source_user_id)
    if not source_user:
        raise HTTPException(status_code=404, detail="Empleado de origen no encontrado")

    target_device = DBService.get_device_by_id(payload.target_device_id)
    if not target_device:
        raise HTTPException(status_code=404, detail="Reloj destino no encontrado")

    if not bool(getattr(target_device, "is_active", True)):
        raise HTTPException(status_code=409, detail="El reloj destino esta inactivo")

    if source_user.device_id == target_device.id:
        raise HTTPException(
            status_code=409,
            detail="Selecciona un reloj diferente al reloj de origen",
        )

    source_role = (
        source_user.role.value
        if hasattr(source_user.role, "value")
        else str(source_user.role or "usuario")
    )

    minimum_uid = DBService.get_next_uid_for_device(target_device.id)
    created_uid = None

    try:
        clock_result = ZKService.create_user_with_next_uid(
            name=source_user.name,
            role=source_role,
            minimum_uid=minimum_uid,
            ip=target_device.ip,
            port=target_device.port,
            password=str(getattr(target_device, "password", "0") or "0"),
        )

        created_user_data = clock_result.get("user", {})
        created_uid = int(created_user_data["uid"])
        created_user_id = str(created_user_data.get("user_id") or created_uid)

        copied_user = DBService.create_user_assignment_copy(
            source_user_id=source_user_id,
            target_device_id=target_device.id,
            uid=created_uid,
            user_id=created_user_id,
        )

        return success(
            data={
                "source_user_id": source_user_id,
                "new_assignment": copied_user.to_dict(),
                "target_device": {
                    "id": target_device.id,
                    "name": target_device.name,
                    "branch_id": target_device.branch_id,
                    "empresa": target_device.empresa,
                },
            },
            message=(
                "Empleado creado en el reloj destino. La asignacion original "
                "y sus asistencias se conservaron"
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        # Si la escritura fisica funciono pero fallo PostgreSQL, se intenta
        # revertir el alta en el reloj para no dejar una asignacion huerfana.
        if created_uid is not None:
            try:
                ZKService.delete_user(
                    created_uid,
                    ip=target_device.ip,
                    port=target_device.port,
                    password=str(getattr(target_device, "password", "0") or "0"),
                )
            except Exception as rollback_error:
                logger.error(
                    "No se pudo revertir el usuario UID %s del reloj destino: %s",
                    created_uid,
                    rollback_error,
                )

        logger.exception("Error creando asignacion en otro reloj")
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo crear al empleado en el reloj destino: {str(e)}",
        )


@router.post(
    "/",
    summary="Crear nuevo usuario",
    description="Crea un nuevo usuario en el reloj biométrico y sincroniza en BD",
    tags=["Usuarios"],
)
def create_user(
    user: UserCreate,
    branch_id: Optional[int] = Query(
        None,
        description="ID de sucursal del reloj seleccionado",
    ),
    device_id: Optional[int] = Query(
        None,
        description="ID del reloj físico donde se creará el empleado",
    ),
):
    """
    Crea un usuario en un dispositivo biométrico y guarda su información en la base de datos.

    :param user: Datos del usuario que se debe crear.
    :type user: UserCreate
    :param branch_id: Identificador opcional de la sucursal seleccionada.
    :type branch_id: int or None
    :param device_id: Identificador opcional del dispositivo donde se creará el usuario.
    :type device_id: int or None
    :return: Respuesta con los datos del usuario y del dispositivo asociado.
    :rtype: dict
    :raises HTTPException: Si el dispositivo no está disponible, el usuario está duplicado o ocurre un error durante la creación.
    """
    try:
        device = get_target_device(branch_id=branch_id, device_id=device_id)

        if not device:
            raise HTTPException(
                status_code=503,
                detail="El reloj seleccionado no existe, está inactivo o no pertenece a la sucursal",
            )

        user_id = str(user.uid)

        result = ZKService.create_user(
            uid=user.uid,
            user_id=user_id,
            name=user.name,
            role=user.role,
            ip=device.ip,
            port=device.port,
            password=str(getattr(device, "password", "0") or "0"),
        )

        saved_user = None

        try:
            saved_user = DBService.save_user(
                uid=user.uid,
                user_id=user_id,
                name=user.name,
                role=user.role,
                sucursal=getattr(device, "location", None),
                branch_id=getattr(device, "branch_id", None),
                device_id=device.id,
                empresa=getattr(device, "empresa", None),
            )
        except Exception as e:
            logger.warning(f"Error al sincronizar usuario {user.uid} en BD: {str(e)}")

        return success(
            data={
                **result["user"],
                "id": getattr(saved_user, "id", None),
                "device_id": device.id,
                "device_name": device.name,
                "branch_id": getattr(device, "branch_id", None),
                "empresa": getattr(device, "empresa", None),
            },
            message=result["message"],
        )

    except DuplicateUserError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Conexión agotada con el dispositivo")
    except ConnectionError:
        raise HTTPException(status_code=503, detail="El dispositivo no está disponible")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error real al crear usuario")
        raise HTTPException(status_code=500, detail=f"Error al crear usuario: {str(e)}")


@router.put(
    "/by-id/{user_id:int}",
    summary="Actualizar usuario por ID interno",
    description="Actualiza el empleado exacto en su reloj asociado y en PostgreSQL",
    tags=["Usuarios"],
)
def update_user_by_id(user_id: int, payload: UserUpdate):
    """
    Actualiza un empleado específico mediante su identificador interno.

    :param user_id: Identificador interno del empleado que se debe actualizar.
    :type user_id: int
    :param payload: Datos del empleado que se deben modificar.
    :type payload: UserUpdate
    :return: Respuesta con el resultado de la actualización.
    :rtype: dict
    :raises HTTPException: Si no se proporcionan cambios, el empleado o su dispositivo no están disponibles o la actualización falla.
    """
    if not payload.user_id and not payload.name and not payload.role:
        raise HTTPException(
            status_code=400,
            detail="Al menos un campo debe ser proporcionado (user_id, name o role)",
        )

    db_user = DBService.get_user_by_id(user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    if db_user.device_id is None:
        raise HTTPException(
            status_code=409,
            detail="El empleado no tiene un reloj asociado",
        )

    device = DBService.get_device_by_id(db_user.device_id)
    if not device or not bool(getattr(device, "is_active", True)):
        raise HTTPException(
            status_code=503,
            detail="El reloj asociado no está disponible",
        )

    try:
        result = ZKService.update_user(
            uid=db_user.uid,
            user_id=payload.user_id or db_user.user_id,
            name=payload.name or db_user.name,
            role=payload.role or (db_user.role.value if hasattr(db_user.role, "value") else str(db_user.role)),
            ip=device.ip,
            port=device.port,
            password=str(getattr(device, "password", "0") or "0"),
        )

        # Actualiza exactamente la misma fila local.
        from app.database.connection import SessionLocal
        db = SessionLocal()
        try:
            current = db.query(type(db_user)).filter(type(db_user).id == user_id).first()
            if not current:
                raise HTTPException(status_code=404, detail="Empleado no encontrado")
            if payload.user_id is not None:
                current.user_id = payload.user_id
            if payload.name is not None:
                current.name = payload.name
            if payload.role is not None:
                from app.models.user import UserRole
                current.role = UserRole(payload.role)
            current.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(current)
        finally:
            db.close()

        return success(
            data={
                "id": user_id,
                "uid": db_user.uid,
                "device_id": db_user.device_id,
                "user": result.get("user"),
            },
            message=result.get("message") or "Usuario actualizado correctamente",
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Conexión agotada con el dispositivo")
    except ConnectionError:
        raise HTTPException(status_code=503, detail="El dispositivo no está disponible")
    except Exception as e:
        logger.exception("Error al actualizar usuario por ID interno")
        raise HTTPException(status_code=500, detail=f"Error al actualizar usuario: {str(e)}")


@router.put(
    "/{uid:int}",
    summary="Actualizar usuario",
    description="Actualiza los datos de un usuario en el reloj y sincroniza en BD",
    tags=["Usuarios"],
)
def update_user(
    uid: int,
    user: UserUpdate,
    branch_id: Optional[int] = Query(
        None,
        description="ID de sucursal para usar el reloj y contraseña correctos",
    ),
):
    """
    Actualiza un usuario en un dispositivo biométrico y sincroniza los cambios con la base de datos.

    :param uid: UID del usuario que se debe actualizar.
    :type uid: int
    :param user: Datos que se deben modificar.
    :type user: UserUpdate
    :param branch_id: Identificador opcional de la sucursal utilizada para seleccionar el dispositivo.
    :type branch_id: int or None
    :return: Respuesta con los datos actualizados del usuario.
    :rtype: dict
    :raises HTTPException: Si no se proporcionan cambios, el dispositivo no está disponible o la actualización falla.
    """
    try:
        if not user.user_id and not user.name and not user.role:
            raise HTTPException(
                status_code=400,
                detail="Al menos un campo debe ser proporcionado (user_id, name o role)",
            )

        device = get_target_device(branch_id)

        if not device:
            raise HTTPException(
                status_code=503,
                detail="No hay un reloj activo disponible para actualizar el empleado",
            )

        result = ZKService.update_user(
            uid=uid,
            user_id=user.user_id,
            name=user.name,
            role=user.role,
            ip=device.ip,
            port=device.port,
            password=str(getattr(device, "password", "0") or "0"),
        )

        try:
            DBService.save_user(
                uid=uid,
                user_id=user.user_id or result.get("user", {}).get("user_id") or str(uid),
                name=user.name or result.get("user", {}).get("name"),
                role=user.role or result.get("user", {}).get("role"),
                sucursal=getattr(device, "location", None),
                branch_id=getattr(device, "branch_id", None),
            )
        except Exception as e:
            logger.warning(f"Error al sincronizar usuario {uid} en BD: {str(e)}")

        return success(
            data=result.get("user"),
            message=result.get("message"),
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
    description="Elimina un usuario del reloj biométrico, pero conserva su ficha y asistencias en BD",
    tags=["Usuarios"],
)
def delete_user(
    uid: int,
    branch_id: Optional[int] = Query(
        None,
        description="ID de sucursal para usar el reloj y contraseña correctos",
    ),
):
    """
    Elimina un usuario del dispositivo biométrico y conserva su información histórica en la base de datos.

    :param uid: UID del usuario que se debe eliminar.
    :type uid: int
    :param branch_id: Identificador opcional de la sucursal utilizada para seleccionar el dispositivo.
    :type branch_id: int or None
    :return: Respuesta con el UID eliminado.
    :rtype: dict
    :raises HTTPException: Si el dispositivo no está disponible, el usuario no existe o la eliminación falla.
    """
    try:
        device = get_target_device(branch_id)

        if not device:
            raise HTTPException(
                status_code=503,
                detail="No hay un reloj activo disponible para eliminar el empleado",
            )

        result = ZKService.delete_user(
            uid,
            ip=device.ip,
            port=device.port,
            password=str(getattr(device, "password", "0") or "0"),
        )

        try:
            DBService.delete_user(uid, device_id=device.id)
        except Exception as e:
            logger.warning(f"Error al eliminar usuario {uid} en BD: {str(e)}")

        return success(
            data={"uid": uid},
            message=result["message"],
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
        raise HTTPException(status_code=500, detail=f"Error al eliminar usuario: {str(e)}")


@router.get(
    "/attendance",
    summary="Obtener registros de asistencia",
    description="Obtiene los registros paginados de asistencia del reloj biométrico y sincroniza en BD",
    tags=["Asistencia"],
)
def get_attendance(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(20, ge=1, le=1000, description="Items por página"),
):
    """
    Obtiene registros de asistencia del dispositivo, los sincroniza con la base de datos y pagina el resultado.

    :param page: Número de página solicitado.
    :type page: int
    :param limit: Cantidad máxima de registros incluidos por página.
    :type limit: int
    :return: Respuesta paginada con los registros de asistencia.
    :rtype: dict
    :raises HTTPException: Si la paginación es inválida, el dispositivo no está disponible o ocurre un error durante la consulta.
    """
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
            message=f"Se obtuvieron {len(asistencias_paginadas)} registros de asistencia",
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
    tags=["Asistencia"],
)
def download_attendance_excel(
    modo: str = Query("todas", description="Opciones: hoy, semana o todas"),
    start_date: Optional[str] = Query(
        None,
        description="Fecha inicial: YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY",
    ),
    end_date: Optional[str] = Query(
        None,
        description="Fecha final: YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY",
    ),
    token: Optional[str] = Query(
        None,
        description="Token opcional enviado desde el frontend",
    ),
):
    """
    Genera un archivo Excel con registros de asistencia filtrados por modo o rango de fechas.

    :param modo: Modo de filtrado aplicado a los registros.
    :type modo: str
    :param start_date: Fecha inicial opcional del rango.
    :type start_date: str or None
    :param end_date: Fecha final opcional del rango.
    :type end_date: str or None
    :param token: Token opcional recibido desde el cliente.
    :type token: str or None
    :return: Respuesta de descarga con el archivo Excel generado.
    :rtype: StreamingResponse
    :raises HTTPException: Si los filtros o el rango son inválidos o no se puede generar el archivo.
    """
    try:
        from app.services.validators import DataValidator

        modo = (modo or "todas").lower().strip()

        if modo not in ("hoy", "semana", "todas"):
            raise HTTPException(
                status_code=400,
                detail="Modo inválido. Usa: hoy, semana o todas",
            )

        if (start_date and not end_date) or (end_date and not start_date):
            raise HTTPException(
                status_code=400,
                detail="Debes enviar start_date y end_date juntos",
            )

        today = datetime.now().date()

        if start_date and end_date:
            parsed_start_date = parse_report_date(start_date)
            parsed_end_date = parse_report_date(end_date)

            start = datetime.combine(parsed_start_date, time.min)
            end = get_safe_end_datetime(parsed_end_date)

        elif modo == "hoy":
            start = datetime.combine(today, time.min)
            end = datetime.now()

        elif modo == "semana":
            start_of_week = today - timedelta(days=today.weekday())
            end_of_week = start_of_week + timedelta(days=6)

            start = datetime.combine(start_of_week, time.min)
            end = get_safe_end_datetime(end_of_week)

        else:
            start = datetime.min
            end = datetime.now()

        DataValidator.validate_date_range(start, end)

        records = DBService.get_attendance_by_date_range(start, end)
        records_dict = [record.to_dict() for record in records]

        excel_bytes = build_attendance_excel(records_dict)

        return StreamingResponse(
            BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=asistencias.xlsx"
            },
        )

    except HTTPException:
        raise
    except DataValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log_exception(logger, e, "Error al descargar asistencias")
        raise HTTPException(status_code=500, detail=f"Error al descargar asistencias: {str(e)}")


@router.get(
    "/attendance/dates",
    summary="Obtener fechas con registros de asistencia",
    description="Obtiene la lista de días en los que hubo registros de asistencia y el total por día",
    tags=["Asistencia"],
)
def get_attendance_dates():
    """
    Obtiene las fechas que contienen registros de asistencia y sus totales.

    :return: Respuesta con el resumen de fechas encontradas.
    :rtype: dict
    """
    try:
        dates_summary = DBService.get_attendance_dates_summary()

        return success(
            data=dates_summary,
            message=f"Se obtuvieron {len(dates_summary)} fechas con registros",
        )

    except Exception as e:
        logger.error(f"Error al obtener fechas con asistencia: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener fechas con asistencia: {str(e)}")


@router.get(
    "/attendance/report",
    summary="Obtener reporte de asistencia por fecha",
    description="Obtiene registros de asistencia de la BD filtrados por rango de fechas",
    tags=["Asistencia"],
)
def get_attendance_report(
    start_date: str = Query(
        ...,
        description="Fecha inicial. Formato: YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY",
    ),
    end_date: str = Query(
        ...,
        description="Fecha final. Formato: YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY",
    ),
):
    """
    Obtiene registros de asistencia filtrados por un rango de fechas.

    :param start_date: Fecha inicial del reporte.
    :type start_date: str
    :param end_date: Fecha final del reporte.
    :type end_date: str
    :return: Respuesta con los registros incluidos en el rango.
    :rtype: dict
    :raises HTTPException: Si las fechas o el rango son inválidos o la consulta falla.
    """
    try:
        from app.services.validators import DataValidator

        parsed_start_date = parse_report_date(start_date)
        parsed_end_date = parse_report_date(end_date)

        start = datetime.combine(parsed_start_date, time.min)
        end = get_safe_end_datetime(parsed_end_date)

        DataValidator.validate_date_range(start, end)

        records = DBService.get_attendance_by_date_range(start, end)
        records_dict = [record.to_dict() for record in records]

        return success(
            data=records_dict,
            message=f"Se obtuvieron {len(records_dict)} registros del {start_date} al {end_date}",
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
    tags=["Asistencia"],
)
def download_attendance_report(
    start_date: str = Query(
        ...,
        description="Fecha inicial. Formato: YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY",
    ),
    end_date: str = Query(
        ...,
        description="Fecha final. Formato: YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY",
    ),
):
    """
    Genera un archivo Excel con registros de asistencia filtrados por fechas.

    :param start_date: Fecha inicial del reporte.
    :type start_date: str
    :param end_date: Fecha final del reporte.
    :type end_date: str
    :return: Respuesta de descarga con el archivo Excel generado.
    :rtype: StreamingResponse
    :raises HTTPException: Si las fechas o el rango son inválidos o no se puede generar el archivo.
    """
    try:
        from app.services.validators import DataValidator

        parsed_start_date = parse_report_date(start_date)
        parsed_end_date = parse_report_date(end_date)

        start = datetime.combine(parsed_start_date, time.min)
        end = get_safe_end_datetime(parsed_end_date)

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
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            },
        )

    except HTTPException:
        raise
    except DataValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al descargar reporte: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al descargar reporte: {str(e)}")