from fastapi import APIRouter
from app.models.user import User
from app.routes import db
from app.services.db_service import DBService
from app.utils.response import success

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)

@router.get("/summary", summary="Resumen general del dashboard")
def dashboard_summary():
    users = DBService.get_all_users_from_db()
    dates = DBService.get_attendance_dates_summary()
    devices = DBService.get_all_devices()
    users = db.query(User).all()

    total_attendance = sum(item["total"] for item in dates)
    connected_devices = len([
        device for device in devices
        if str(device.status).lower() == "conectado"
    ])

    data = {
        "total_users": len(users),
        "total_attendance": total_attendance,
        "total_devices": len(devices),
        "connected_devices": connected_devices,
        "active_branches": len(set(
            device.location for device in devices
            if device.location
        )),
    }

    return success(
        data=data,
        message="Resumen del dashboard obtenido correctamente"
    )

@router.get("/activity", summary="Actividad reciente del dashboard")
def dashboard_activity():
    records = DBService.get_attendance_by_date_range(
        __import__("datetime").datetime.min,
        __import__("datetime").datetime.max
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