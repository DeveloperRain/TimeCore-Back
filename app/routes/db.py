from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, time
from app.services.db_service import DBService
from app.utils.response import success
from pydantic import BaseModel
from typing import Optional
from fastapi.responses import StreamingResponse
from io import BytesIO
from app.services.excel_service import build_attendance_excel

router = APIRouter(
    prefix="/db",
    tags=["Base de Datos"]
)

DATE_FORMATS = ("%d-%m-%Y", "%d/%m/%Y")


def parse_date(value: str):
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue

    raise HTTPException(
        status_code=400,
        detail="Formato de fecha inválido. Usa DD-MM-YYYY o DD/MM/YYYY"
    )


@router.get("/users", summary="Obtener usuarios desde PostgreSQL")
def get_users_from_db():
    users = DBService.get_all_users_from_db()

    data = [
        {
            "uid": user.uid,
            "user_id": user.user_id,
            "name": user.name,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }
        for user in users
    ]

    return success(
        data=data,
        message=f"Se obtuvieron {len(data)} usuarios desde la base de datos"
    )


@router.get("/attendance", summary="Obtener asistencias desde PostgreSQL")
def get_attendance_from_db(
    limit: int = Query(100, ge=1, le=1000),
):
    records = DBService.get_attendance_by_date_range(
        datetime.min,
        datetime.max
    )

    records = records[:limit]

    data = [
        {
            "id": record.id,
            "uid": record.uid,
            "user_id": record.user_id,
            "name": record.name,
            "timestamp": record.timestamp.isoformat() if record.timestamp else None,
            "status": record.status,
        }
        for record in records
    ]

    return success(
        data=data,
        message=f"Se obtuvieron {len(data)} asistencias desde la base de datos"
    )


@router.get("/attendance/dates", summary="Obtener fechas con asistencias desde PostgreSQL")
def get_attendance_dates_from_db():
    dates = DBService.get_attendance_dates_summary()

    return success(
        data=dates,
        message=f"Se obtuvieron {len(dates)} fechas con registros"
    )


@router.get("/attendance/report", summary="Obtener reporte de asistencias desde PostgreSQL")
def get_attendance_report_from_db(
    start_date: str = Query(..., description="Fecha inicial DD-MM-YYYY o DD/MM/YYYY"),
    end_date: str = Query(..., description="Fecha final DD-MM-YYYY o DD/MM/YYYY"),
):
    start = datetime.combine(parse_date(start_date), time.min)
    end = datetime.combine(parse_date(end_date), time.max)

    records = DBService.get_attendance_by_date_range(start, end)

    data = [
        {
            "id": record.id,
            "uid": record.uid,
            "user_id": record.user_id,
            "name": record.name,
            "timestamp": record.timestamp.isoformat() if record.timestamp else None,
            "status": record.status,
        }
        for record in records
    ]

    return success(
        data=data,
        message=f"Se obtuvieron {len(data)} registros desde {start_date} hasta {end_date}"
    )

class DeviceCreate(BaseModel):
    nombre: str
    ip: str
    puerto: int = 4370
    sucursal: Optional[str] = None
    ubicacion: Optional[str] = None

class DeviceUpdate(BaseModel):
    nombre: Optional[str] = None
    ip: Optional[str] = None
    puerto: Optional[int] = None
    sucursal: Optional[str] = None
    ubicacion: Optional[str] = None
    activo: Optional[bool] = None

@router.get("/devices", summary="Obtener relojes registrados desde PostgreSQL")
def get_devices_from_db():
    devices = DBService.get_all_devices()

    data = [
        {
            "id": device.id,
            "nombre": device.name,
            "ip": device.ip,
            "puerto": device.port,
            "sucursal": device.location,
            "ubicacion": device.description,
            "activo": device.is_active,
            "estado": device.status,
            "ultima_sincronizacion": device.last_connection.isoformat()
            if device.last_connection
            else None,
            "created_at": device.created_at.isoformat() if device.created_at else None,
            "updated_at": device.updated_at.isoformat() if device.updated_at else None,
        }
        for device in devices
    ]

    return success(
        data=data,
        message=f"Se obtuvieron {len(data)} relojes registrados"
    )


@router.post("/devices", summary="Registrar reloj biométrico en PostgreSQL")
def create_device(device: DeviceCreate):
    saved = DBService.save_device(
        nombre=device.nombre,
        ip=device.ip,
        puerto=device.puerto,
        sucursal=device.sucursal,
        ubicacion=device.ubicacion,
    )

    DBService.create_log(
    accion="Reloj agregado",
    detalle=f"Se registró el reloj {saved.name} ({saved.ip})"
)

    return success(
        data={
            "id": saved.id,
            "nombre": saved.name,
            "ip": saved.ip,
            "puerto": saved.port,
            "sucursal": saved.location,
            "ubicacion": saved.description,
            "estado": saved.status,
            "activo": saved.is_active,
        },
        message="Reloj registrado correctamente"
    )


@router.get("/devices/{device_id}", summary="Obtener reloj por ID desde PostgreSQL")
def get_device_by_id(device_id: int):
    device = DBService.get_device_by_id(device_id)

    if not device:
        raise HTTPException(status_code=404, detail="Reloj no encontrado")

    return success(
        data={
            "id": device.id,
            "nombre": device.name,
            "ip": device.ip,
            "puerto": device.port,
            "sucursal": device.location,
            "ubicacion": device.description,
            "activo": device.is_active,
            "estado": device.status,
            "ultima_sincronizacion": device.last_connection.isoformat()
            if device.last_connection
            else None,
        },
        message="Reloj obtenido correctamente"
    )
@router.put("/devices/{device_id}", summary="Actualizar reloj biométrico")
def update_device(device_id: int, device: DeviceUpdate):
    updated = DBService.update_device(
        device_id=device_id,
        nombre=device.nombre,
        ip=device.ip,
        puerto=device.puerto,
        sucursal=device.sucursal,
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
        data={
            "id": updated.id,
            "nombre": updated.name,
            "ip": updated.ip,
            "puerto": updated.port,
            "sucursal": updated.location,
            "ubicacion": updated.description,
            "activo": updated.is_active,
            "estado": updated.status,
        },
        message="Reloj actualizado correctamente"
    )

@router.delete("/devices/{device_id}", summary="Eliminar reloj biométrico")
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
        accion="Reloj eliminado",
        detalle=f"Se eliminó el reloj {device_name} ({device_ip})"
    )

    return success(
        data={"id": device_id},
        message="Reloj eliminado correctamente"
    )

@router.get("/attendance/download", summary="Descargar asistencias desde PostgreSQL en Excel")
def download_attendance_from_db():
    records = DBService.get_attendance_by_date_range(
        datetime.min,
        datetime.max
    )

    records_dict = [
        {
            "uid": record.uid,
            "user_id": record.user_id,
            "name": record.name,
            "timestamp": record.timestamp,
            "status": record.status,
        }
        for record in records
    ]

    excel_bytes = build_attendance_excel(records_dict)

    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=asistencias_bd.xlsx"}
    )

@router.get("/attendance/report/download", summary="Descargar reporte de asistencias desde PostgreSQL en Excel")
def download_attendance_report_from_db(
    start_date: str = Query(..., description="Fecha inicial DD-MM-YYYY o DD/MM/YYYY"),
    end_date: str = Query(..., description="Fecha final DD-MM-YYYY o DD/MM/YYYY"),
):
    start = datetime.combine(parse_date(start_date), time.min)
    end = datetime.combine(parse_date(end_date), time.max)

    records = DBService.get_attendance_by_date_range(start, end)

    records_dict = [
        {
            "uid": record.uid,
            "user_id": record.user_id,
            "name": record.name,
            "timestamp": record.timestamp,
            "status": record.status,
        }
        for record in records
    ]

    excel_bytes = build_attendance_excel(records_dict)

    filename = f"asistencias_{start_date.replace('/', '-')}_a_{end_date.replace('/', '-')}.xlsx"

    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )