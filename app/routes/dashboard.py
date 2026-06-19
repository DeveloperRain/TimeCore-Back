from datetime import datetime

from fastapi import APIRouter

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


@router.get("/summary", summary="Resumen general del dashboard")
def dashboard_summary():
    db = SessionLocal()

    try:
        total_users = db.query(User).count()

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
def dashboard_activity():
    records = DBService.get_attendance_by_date_range(
        datetime.min,
        datetime.max
    )

    records = records[:10]

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
        message=f"Se obtuvieron {len(data)} actividades recientes"
    )