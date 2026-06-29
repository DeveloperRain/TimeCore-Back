from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_

from app.database.connection import SessionLocal
from app.models.user import User
from app.models.device import Device
from app.models.attendance import AttendanceRecord
from app.models.branch import Branch
from app.services.db_service import DBService
from app.utils.response import success

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)


def attendance_to_dict(record):
    return {
        "id": record.id,
        "uid": record.uid,
        "user_id": record.user_id,
        "name": record.name,
        "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        "status": record.status,
        "branch_id": getattr(record, "branch_id", None),
        "device_id": getattr(record, "device_id", None),
        "device_code": getattr(record, "device_code", None),
    }


@router.get("/summary", summary="Resumen general del dashboard")
def dashboard_summary(
    branch_id: Optional[int] = Query(
        None,
        description="ID de sucursal para filtrar el dashboard. Si no se envía, muestra el resumen general.",
    )
):
    db = SessionLocal()

    try:
        if branch_id is not None:
            branch = db.query(Branch).filter(Branch.id == branch_id).first()

            if not branch:
                raise HTTPException(status_code=404, detail="Sucursal no encontrada")

            users = DBService.get_users_by_branch(branch_id)
            devices = DBService.get_devices_by_branch(branch_id)
            attendance = DBService.get_attendance_by_branch(branch_id)

            connected_devices = [
                device
                for device in devices
                if getattr(device, "is_active", False) is True
                and getattr(device, "status", "") == "Conectado"
            ]

            return success(
                data={
                    "branch": {
                        "id": branch.id,
                        "name": branch.name,
                        "address": branch.address,
                        "is_active": branch.is_active,
                        "status": getattr(branch, "status", "Activo"),
                    },
                    "total_empleados": len(users),
                    "relojes_conectados": len(connected_devices),
                    "total_relojes": len(devices),
                    "asistencias_registradas": len(attendance),
                    "sucursales_activas": 1 if branch.is_active else 0,
                },
                message=f"Resumen del dashboard de {branch.name} obtenido correctamente"
            )

        total_users = db.query(User).filter(User.deleted_at.is_(None)).count()

        total_devices = db.query(Device).count()

        connected_devices = db.query(Device).filter(
            Device.is_active == True,
            Device.status == "Conectado"
        ).count()

        total_attendance = db.query(AttendanceRecord).count()

        active_branches = db.query(Branch).filter(
            Branch.is_active == True
        ).count()

        return success(
            data={
                "total_empleados": total_users,
                "relojes_conectados": connected_devices,
                "total_relojes": total_devices,
                "asistencias_registradas": total_attendance,
                "sucursales_activas": active_branches,
            },
            message="Resumen del dashboard obtenido correctamente"
        )

    finally:
        db.close()


@router.get("/activity", summary="Actividad reciente del dashboard")
def dashboard_activity(
    branch_id: Optional[int] = Query(
        None,
        description="ID de sucursal para filtrar actividad reciente. Si no se envía, muestra actividad general.",
    )
):
    if branch_id is not None:
        branch = DBService.get_branch_by_id(branch_id)

        if not branch:
            raise HTTPException(status_code=404, detail="Sucursal no encontrada")

        records = DBService.get_attendance_by_branch(branch_id)
        records = records[:10]

        data = [attendance_to_dict(record) for record in records]

        return success(
            data=data,
            message=f"Se obtuvieron {len(data)} actividades recientes de {branch.name}"
        )

    records = DBService.get_attendance_by_date_range(
        datetime.min,
        datetime.max
    )

    records = records[:10]

    data = [attendance_to_dict(record) for record in records]

    return success(
        data=data,
        message=f"Se obtuvieron {len(data)} actividades recientes"
    )