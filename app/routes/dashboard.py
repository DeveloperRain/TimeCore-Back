from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, func

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

            total_users = db.query(User).filter(User.branch_id == branch_id).count()
            total_devices = db.query(Device).filter(Device.branch_id == branch_id).count()
            connected_devices = db.query(Device).filter(
                Device.branch_id == branch_id,
                Device.is_active == True,
                Device.status == "Conectado",
            ).count()
            total_attendance = db.query(AttendanceRecord).filter(
                AttendanceRecord.branch_id == branch_id
            ).count()

            return success(
                data={
                    "branch": {
                        "id": branch.id,
                        "name": branch.name,
                        "address": branch.address,
                        "is_active": branch.is_active,
                        "status": getattr(branch, "status", "Activo"),
                    },
                    "total_empleados": total_users,
                    "relojes_conectados": connected_devices,
                    "total_relojes": total_devices,
                    "asistencias_registradas": total_attendance,
                    "sucursales_activas": 1 if branch.is_active else 0,
                },
                message=f"Resumen del dashboard de {branch.name} obtenido correctamente"
            )

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

        employee_counts = dict(
            db.query(User.branch_id, func.count(User.id))
            .filter(User.branch_id.is_not(None))
            .group_by(User.branch_id)
            .all()
        )
        employees_by_branch = [
            {
                "id": branch.id,
                "nombre": branch.name,
                "empleados": int(employee_counts.get(branch.id, 0)),
            }
            for branch in db.query(Branch).order_by(Branch.name.asc()).all()
        ]

        return success(
            data={
                "total_empleados": total_users,
                "relojes_conectados": connected_devices,
                "total_relojes": total_devices,
                "asistencias_registradas": total_attendance,
                "sucursales_activas": active_branches,
                "empleados_por_sucursal": employees_by_branch,
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
    ),
    limit: int = Query(8, ge=1, le=20),
):
    db = SessionLocal()
    try:
        query = db.query(AttendanceRecord)

        if branch_id is not None:
            branch = db.query(Branch).filter(Branch.id == branch_id).first()
            if not branch:
                raise HTTPException(status_code=404, detail="Sucursal no encontrada")
            query = query.filter(AttendanceRecord.branch_id == branch_id)

        records = (
            query.order_by(AttendanceRecord.timestamp.desc())
            .limit(limit)
            .all()
        )
        data = [attendance_to_dict(record) for record in records]
        return success(data=data, message=f"Se obtuvieron {len(data)} actividades recientes")
    finally:
        db.close()
