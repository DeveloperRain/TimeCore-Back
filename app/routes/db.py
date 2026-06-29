from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, time, timedelta
from pydantic import BaseModel
from typing import Optional
from fastapi.responses import StreamingResponse
from io import BytesIO

from app.services.db_service import DBService
from app.utils.response import success
from app.services.excel_service import build_attendance_excel


router = APIRouter(
    prefix="/db",
    tags=["Base de Datos"]
)

DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y")


def parse_date(value: str):
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue

    raise HTTPException(
        status_code=400,
        detail="Formato de fecha inválido. Usa YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY"
    )


def user_to_dict(user):
    return {
        "uid": user.uid,
        "user_id": user.user_id,
        "name": user.name,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        "status": user.status if hasattr(user, "status") else "Activo",
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "sucursal": user.sucursal if hasattr(user, "sucursal") else None,
        "email": user.email if hasattr(user, "email") else None,
        "branch_id": getattr(user, "branch_id", None),
        "device_id": getattr(user, "device_id", None),
        "device_code": getattr(user, "device_code", None),
    }


def attendance_to_dict(record):
    return {
        "id": record.id,
        "uid": record.uid,
        "user_id": record.user_id,
        "name": record.name,
        "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        "status": record.status,
        "synced_at": record.synced_at.isoformat() if getattr(record, "synced_at", None) else None,
        "branch_id": getattr(record, "branch_id", None),
        "device_id": getattr(record, "device_id", None),
        "device_code": getattr(record, "device_code", None),
    }


def attendance_to_excel_dict(record):
    return {
        "uid": record.uid,
        "user_id": record.user_id,
        "name": record.name,
        "timestamp": record.timestamp,
        "status": record.status,
    }


def device_to_dict(device):
    return {
        "id": device.id,
        "nombre": device.name,
        "name": device.name,
        "ip": device.ip,
        "ip_address": device.ip,
        "puerto": device.port,
        "port": device.port,
        "sucursal": device.location,
        "ubicacion": device.description,
        "location": device.location,
        "description": device.description,
        "activo": device.is_active,
        "is_active": device.is_active,
        "estado": device.status,
        "status": device.status,
        "branch_id": getattr(device, "branch_id", None),
        "ultima_sincronizacion": device.last_connection.isoformat()
        if device.last_connection
        else None,
        "created_at": device.created_at.isoformat() if device.created_at else None,
        "updated_at": device.updated_at.isoformat() if device.updated_at else None,
    }


def get_branch_or_404(branch_id: int):
    branch = DBService.get_branch_by_id(branch_id)

    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    return branch


def filter_records_by_range(records, start_datetime: datetime, end_datetime: datetime):
    return [
        record
        for record in records
        if record.timestamp
        and record.timestamp >= start_datetime
        and record.timestamp <= end_datetime
    ]


def get_attendance_records(
    start_datetime: datetime = datetime.min,
    end_datetime: datetime = datetime.max,
    branch_id: Optional[int] = None,
):
    if branch_id is not None:
        get_branch_or_404(branch_id)
        records = DBService.get_attendance_by_branch(branch_id)
        return filter_records_by_range(records, start_datetime, end_datetime)

    return DBService.get_attendance_by_date_range(
        start_datetime,
        end_datetime
    )


@router.get("/users", summary="Obtener usuarios desde PostgreSQL")
def get_users_from_db(
    branch_id: Optional[int] = Query(
        None,
        description="ID de sucursal para filtrar empleados"
    )
):
    if branch_id is not None:
        get_branch_or_404(branch_id)
        users = DBService.get_users_by_branch(branch_id)
    else:
        users = DBService.get_all_users_from_db()

    data = [user_to_dict(user) for user in users]

    return success(
        data=data,
        message=f"Se obtuvieron {len(data)} usuarios desde la base de datos"
    )


@router.get("/attendance", summary="Obtener asistencias desde PostgreSQL")
def get_attendance_from_db(
    limit: int = Query(100, ge=1, le=1000),
    branch_id: Optional[int] = Query(
        None,
        description="ID de sucursal para filtrar asistencias"
    )
):
    records = get_attendance_records(branch_id=branch_id)
    records = records[:limit]

    data = [attendance_to_dict(record) for record in records]

    return success(
        data=data,
        message=f"Se obtuvieron {len(data)} asistencias desde la base de datos"
    )


@router.get("/attendance/dates", summary="Obtener fechas con asistencias desde PostgreSQL")
def get_attendance_dates_from_db(
    branch_id: Optional[int] = Query(
        None,
        description="ID de sucursal para filtrar fechas con asistencia"
    )
):
    if branch_id is None:
        dates = DBService.get_attendance_dates_summary()

        return success(
            data=dates,
            message=f"Se obtuvieron {len(dates)} fechas con registros"
        )

    get_branch_or_404(branch_id)
    records = DBService.get_attendance_by_branch(branch_id)

    grouped = {}

    for record in records:
        if not record.timestamp:
            continue

        fecha = record.timestamp.date().isoformat()
        grouped[fecha] = grouped.get(fecha, 0) + 1

    dates = [
        {
            "fecha": fecha,
            "total": total,
        }
        for fecha, total in sorted(grouped.items(), reverse=True)
    ]

    return success(
        data=dates,
        message=f"Se obtuvieron {len(dates)} fechas con registros"
    )


@router.get("/attendance/report", summary="Obtener reporte de asistencias desde PostgreSQL")
def get_attendance_report_from_db(
    start_date: str = Query(..., description="Fecha inicial YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY"),
    end_date: str = Query(..., description="Fecha final YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY"),
    branch_id: Optional[int] = Query(
        None,
        description="ID de sucursal para filtrar reporte"
    )
):
    start = datetime.combine(parse_date(start_date), time.min)
    end = datetime.combine(parse_date(end_date), time.max)

    records = get_attendance_records(
        start_datetime=start,
        end_datetime=end,
        branch_id=branch_id,
    )

    data = [attendance_to_dict(record) for record in records]

    return success(
        data=data,
        message=f"Se obtuvieron {len(data)} registros desde {start_date} hasta {end_date}"
    )


@router.get("/attendance/today", summary="Obtener asistencias del día actual")
def get_today_attendance(
    branch_id: Optional[int] = Query(
        None,
        description="ID de sucursal para filtrar asistencias de hoy"
    )
):
    today = datetime.now().date()

    start_datetime = datetime.combine(today, time.min)
    end_datetime = datetime.combine(today, time.max)

    records = get_attendance_records(
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        branch_id=branch_id,
    )

    data = [attendance_to_dict(record) for record in records]

    return success(
        data=data,
        message=f"Se obtuvieron {len(data)} asistencias de hoy"
    )


@router.get("/attendance/week", summary="Obtener asistencias de esta semana")
def get_week_attendance(
    branch_id: Optional[int] = Query(
        None,
        description="ID de sucursal para filtrar asistencias de la semana"
    )
):
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    start_datetime = datetime.combine(start_of_week, time.min)
    end_datetime = datetime.combine(end_of_week, time.max)

    records = get_attendance_records(
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        branch_id=branch_id,
    )

    data = [attendance_to_dict(record) for record in records]

    return success(
        data=data,
        message=f"Se obtuvieron {len(data)} asistencias de esta semana"
    )


class DeviceCreate(BaseModel):
    nombre: str
    ip: str
    puerto: int = 4370
    sucursal: Optional[str] = None
    ubicacion: Optional[str] = None
    branch_id: Optional[int] = None


class DeviceUpdate(BaseModel):
    nombre: Optional[str] = None
    ip: Optional[str] = None
    puerto: Optional[int] = None
    sucursal: Optional[str] = None
    ubicacion: Optional[str] = None
    activo: Optional[bool] = None
    branch_id: Optional[int] = None


@router.get("/devices", summary="Obtener relojes registrados desde PostgreSQL")
def get_devices_from_db(
    branch_id: Optional[int] = Query(
        None,
        description="ID de sucursal para filtrar relojes"
    )
):
    if branch_id is not None:
        get_branch_or_404(branch_id)
        devices = DBService.get_devices_by_branch(branch_id)
    else:
        devices = DBService.get_all_devices()

    data = [device_to_dict(device) for device in devices]

    return success(
        data=data,
        message=f"Se obtuvieron {len(data)} relojes registrados"
    )


@router.post("/devices", summary="Registrar reloj biométrico en PostgreSQL")
def create_device(device: DeviceCreate):
    sucursal = device.sucursal

    if device.branch_id is not None:
        branch = get_branch_or_404(device.branch_id)
        sucursal = branch.name

    saved = DBService.save_device(
        nombre=device.nombre,
        ip=device.ip,
        puerto=device.puerto,
        sucursal=sucursal,
        ubicacion=device.ubicacion,
    )

    DBService.create_log(
        accion="Reloj agregado",
        detalle=f"Se registró el reloj {saved.name} ({saved.ip})"
    )

    return success(
        data=device_to_dict(saved),
        message="Reloj registrado correctamente"
    )


@router.get("/devices/{device_id}", summary="Obtener reloj por ID desde PostgreSQL")
def get_device_by_id(device_id: int):
    device = DBService.get_device_by_id(device_id)

    if not device:
        raise HTTPException(status_code=404, detail="Reloj no encontrado")

    return success(
        data=device_to_dict(device),
        message="Reloj obtenido correctamente"
    )


@router.put("/devices/{device_id}", summary="Actualizar reloj biométrico")
def update_device(device_id: int, device: DeviceUpdate):
    sucursal = device.sucursal

    if device.branch_id is not None:
        branch = get_branch_or_404(device.branch_id)
        sucursal = branch.name

    updated = DBService.update_device(
        device_id=device_id,
        nombre=device.nombre,
        ip=device.ip,
        puerto=device.puerto,
        sucursal=sucursal,
        ubicacion=device.ubicacion,
        activo=device.activo,
    )

    if not updated:
        raise HTTPException(status_code=404, detail="Reloj no encontrado")

    DBService.create_log(
        accion="Reloj actualizado",
        detalle=f"Se actualizó el reloj {updated.name} ({updated.ip})"
    )

    return success(
        data=device_to_dict(updated),
        message="Reloj actualizado correctamente"
    )


@router.delete("/devices/{device_id}", summary="Inactivar reloj biométrico")
def delete_device(device_id: int):
    device = DBService.get_device_by_id(device_id)

    if not device:
        raise HTTPException(status_code=404, detail="Reloj no encontrado")

    device_name = device.name
    device_ip = device.ip

    deleted = DBService.delete_device(device_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Reloj no encontrado")

    DBService.create_log(
        accion="Reloj inactivado",
        detalle=f"Se inactivó el reloj {device_name} ({device_ip})"
    )

    return success(
        data={"id": device_id},
        message="Reloj inactivado correctamente"
    )


@router.put("/devices/{device_id}/activate", summary="Activar reloj biométrico")
def activate_device(device_id: int):
    device = DBService.get_device_by_id(device_id)

    if not device:
        raise HTTPException(status_code=404, detail="Reloj no encontrado")

    activated = DBService.activate_device(device_id)

    if not activated:
        raise HTTPException(status_code=404, detail="Reloj no encontrado")

    DBService.create_log(
        accion="Reloj activado",
        detalle=f"Se activó el reloj {device.name} ({device.ip})"
    )

    return success(
        data={"id": device_id},
        message="Reloj activado correctamente"
    )


@router.get("/attendance/download", summary="Descargar asistencias desde PostgreSQL en Excel")
def download_attendance_from_db(
    branch_id: Optional[int] = Query(
        None,
        description="ID de sucursal para filtrar descarga"
    )
):
    records = get_attendance_records(branch_id=branch_id)

    records_dict = [attendance_to_excel_dict(record) for record in records]

    excel_bytes = build_attendance_excel(records_dict)

    filename = "asistencias_bd.xlsx"

    if branch_id is not None:
        branch = get_branch_or_404(branch_id)
        filename = f"asistencias_{branch.name.replace(' ', '_')}.xlsx"

    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/attendance/report/download", summary="Descargar reporte de asistencias desde PostgreSQL en Excel")
def download_attendance_report_from_db(
    start_date: str = Query(..., description="Fecha inicial YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY"),
    end_date: str = Query(..., description="Fecha final YYYY-MM-DD, DD-MM-YYYY o DD/MM/YYYY"),
    branch_id: Optional[int] = Query(
        None,
        description="ID de sucursal para filtrar descarga"
    )
):
    start = datetime.combine(parse_date(start_date), time.min)
    end = datetime.combine(parse_date(end_date), time.max)

    records = get_attendance_records(
        start_datetime=start,
        end_datetime=end,
        branch_id=branch_id,
    )

    records_dict = [attendance_to_excel_dict(record) for record in records]

    excel_bytes = build_attendance_excel(records_dict)

    filename = f"asistencias_{start_date.replace('/', '-')}_a_{end_date.replace('/', '-')}.xlsx"

    if branch_id is not None:
        branch = get_branch_or_404(branch_id)
        filename = (
            f"asistencias_{branch.name.replace(' ', '_')}_"
            f"{start_date.replace('/', '-')}_a_{end_date.replace('/', '-')}.xlsx"
        )

    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


class UserStatusUpdate(BaseModel):
    status: str


@router.put("/users/{uid}/status", summary="Actualizar estado de empleado")
def update_user_status(uid: int, payload: UserStatusUpdate):
    allowed = ["Activo", "Inactivo", "Baja"]

    if payload.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail="Estado inválido. Usa Activo, Inactivo o Baja"
        )

    user = DBService.update_user_status(uid, payload.status)

    if not user:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")

    DBService.create_log(
        accion="Estado de empleado actualizado",
        detalle=f"Empleado {user.name} ({user.user_id}) cambió a estado {payload.status}"
    )

    return success(
        data={
            "uid": user.uid,
            "user_id": user.user_id,
            "name": user.name,
            "status": user.status,
        },
        message="Estado de empleado actualizado correctamente"
    )


class UserProfileUpdate(BaseModel):
    role: Optional[str] = None
    sucursal: Optional[str] = None
    email: Optional[str] = None
    branch_id: Optional[int] = None


@router.put("/users/{uid}/profile", summary="Actualizar perfil de empleado")
def update_user_profile(uid: int, payload: UserProfileUpdate):
    sucursal = payload.sucursal

    if payload.branch_id is not None:
        branch = get_branch_or_404(payload.branch_id)
        sucursal = branch.name

    user = DBService.update_user_profile(
        uid=uid,
        role=payload.role,
        sucursal=sucursal,
        email=payload.email,
    )

    if not user:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")

    DBService.create_log(
        accion="Perfil de empleado actualizado",
        detalle=f"Empleado {user.name} ({user.user_id}) actualizado"
    )

    return success(
        data={
            "uid": user.uid,
            "user_id": user.user_id,
            "name": user.name,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "sucursal": user.sucursal,
            "email": user.email,
            "branch_id": getattr(user, "branch_id", None),
        },
        message="Perfil de empleado actualizado correctamente"
    )