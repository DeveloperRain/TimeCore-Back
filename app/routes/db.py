from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, time
from app.services.db_service import DBService
from app.utils.response import success

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