from fastapi import APIRouter, HTTPException
from app.services.zk_service import ZKService
from app.services.db_service import DBService
from app.utils.response import success
from app.config.logger import get_logger, log_exception
from datetime import datetime
from zoneinfo import ZoneInfo

logger = get_logger("routes.sync")

router = APIRouter(
    prefix="/sync",
    tags=["Sincronización"]
)


def mexico_now():
    return datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None)


def format_event_time(value=None):
    try:
        if value is None:
            dt = mexico_now()
        elif isinstance(value, datetime):
            dt = value
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

        return dt.strftime("%H:%M:%S")
    except Exception:
        return mexico_now().strftime("%H:%M:%S")


def sync_registered_device(device, include_events: bool = False):
    events = []

    def add_event(message, event_type="info", time_value=None, payload=None):
        if not include_events:
            return

        event = {
            "time": format_event_time(time_value),
            "type": event_type,
            "message": message,
        }

        if payload is not None:
            event["payload"] = payload

        events.append(event)

    add_event(f"Conectando a '{device.ip}'", "connection")

    usuarios = ZKService.get_all_users(
        ip=device.ip,
        port=device.port
    )

    add_event(f"{len(usuarios)} empleados descargados", "users_summary")

    users_count = 0

    for user in usuarios:
        DBService.save_user(
            uid=user["uid"],
            user_id=user["user_id"],
            name=user["name"],
            role=user["role"]
        )
        users_count += 1

        add_event(
            f"Empleado descargado: {user['name']} | UID {user['uid']} | Código {user['user_id']} | Rol {user['role']}",
            "user",
            payload=user,
        )

    add_event("Descargando eventos de asistencia", "attendance_start")

    asistencias = ZKService.get_attendance_records(
        ip=device.ip,
        port=device.port
    )

    attendance_count = DBService.save_bulk_attendance(asistencias)

    for attendance in asistencias:
        timestamp = attendance.get("timestamp")
        add_event(
            f"Asistencia: {attendance.get('name', 'Desconocido')} | Código {attendance.get('user_id', '')} | {timestamp} | {attendance.get('status', '')}",
            "attendance",
            time_value=timestamp,
            payload=attendance,
        )

    DBService.update_device_status(
        device_id=device.id,
        estado="Conectado",
        ultima_sincronizacion=mexico_now()
    )

    DBService.create_log(
        accion="Sincronización de reloj",
        detalle=f"Se sincronizó {device.name} ({device.ip}). Usuarios: {users_count}, asistencias nuevas: {attendance_count}"
    )

    add_event(
        f"{len(asistencias)} eventos descargados / {attendance_count} eventos nuevos",
        "summary",
    )

    return {
        "device_id": device.id,
        "device_name": device.name,
        "ip": device.ip,
        "users_synced": users_count,
        "attendance_synced": attendance_count,
        "attendance_downloaded": len(asistencias),
        "events": events,
    }


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
    
@router.post("/device/{device_id}", summary="Sincronizar reloj seleccionado por ID")
def sync_device_by_id(device_id: int):
    try:
        device = DBService.get_device_by_id(device_id)

        if not device:
            raise HTTPException(status_code=404, detail="Reloj no encontrado")

        result = sync_registered_device(device, include_events=True)

        return success(
            data=result,
            message="Reloj sincronizado correctamente"
        )

    except HTTPException:
        raise

    except Exception as e:
        try:
            DBService.update_device_status(
                device_id=device_id,
                estado="Desconectado"
            )

            DBService.create_log(
                accion="Error de sincronización",
                detalle=f"No se pudo sincronizar el reloj ID {device_id}: {str(e)}"
            )

        except Exception:
            pass

        log_exception(logger, e, "Error al sincronizar reloj por ID")

        raise HTTPException(
            status_code=500,
            detail=f"Error al sincronizar reloj: {str(e)}"
        )


@router.post("/devices/all", summary="Sincronizar todos los relojes registrados")
def sync_all_registered_devices():
    devices = DBService.get_all_devices()
    active_devices = [
        device
        for device in devices
        if getattr(device, "is_active", True)
        and str(getattr(device, "status", "")).strip().lower()
        not in ("inactivo", "desconectado")
    ]
    skipped_devices = len(devices) - len(active_devices)

    results = []
    failed = []

    for device in active_devices:
        try:
            results.append(sync_registered_device(device))
        except Exception as e:
            try:
                DBService.update_device_status(
                    device_id=device.id,
                    estado="Desconectado"
                )

                DBService.create_log(
                    accion="Error de sincronización",
                    detalle=f"No se pudo sincronizar {device.name} ({device.ip}): {str(e)}"
                )
            except Exception:
                pass

            failed.append({
                "device_id": device.id,
                "device_name": device.name,
                "ip": device.ip,
                "error": str(e),
            })

            log_exception(logger, e, f"Error al sincronizar reloj {device.id}")

    users_total = sum(item["users_synced"] for item in results)
    attendance_total = sum(item["attendance_synced"] for item in results)

    return success(
        data={
            "total_devices": len(devices),
            "active_devices": len(active_devices),
            "skipped_devices": skipped_devices,
            "synced_devices": len(results),
            "failed_devices": len(failed),
            "users_synced": users_total,
            "attendance_synced": attendance_total,
            "results": results,
            "failed": failed,
        },
        message=(
            "Se sincronizaron todos los relojes disponibles"
            if not failed
            else "Sincronización finalizada con algunos relojes sin conexión"
        )
    )
   
