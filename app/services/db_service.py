"""Servicio de operaciones en base de datos."""
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.database.connection import SessionLocal
from app.models.user import User, UserRole
from app.models.attendance import AttendanceRecord
from app.config.logger import get_logger

logger = get_logger("services.db")

class DBService:
    """Servicio de persistencia en PostgreSQL."""

    @staticmethod
    def save_user(uid: int, user_id: str, name: str, role: str, db: Optional[Session] = None) -> User:
        """Guarda o actualiza un usuario en la BD."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            existing_user = db.query(User).filter(User.uid == uid).first()

            if existing_user:
                existing_user.user_id = user_id
                existing_user.name = name
                existing_user.role = UserRole(role) if role else UserRole.usuario
                existing_user.updated_at = datetime.utcnow()
                db.commit()
                logger.info(f"Usuario UID {uid} actualizado en BD")
                return existing_user

            new_user = User(
                uid=uid,
                user_id=user_id,
                name=name,
                role=UserRole(role) if role else UserRole.usuario
            )
            db.add(new_user)
            db.commit()
            logger.info(f"Usuario UID {uid} guardado en BD")
            return new_user

        except Exception as e:
            db.rollback()
            logger.error(f"Error al guardar usuario {uid}: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()

    @staticmethod
    def delete_user(uid: int, db: Optional[Session] = None) -> bool:
        """Elimina un usuario de la BD conservando sus asistencias historicas."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            user = db.query(User).filter(User.uid == uid).first()
            if user:
                db.query(AttendanceRecord).filter(AttendanceRecord.uid == uid).update(
                    {AttendanceRecord.uid: None},
                    synchronize_session=False
                )
                db.delete(user)
                db.commit()
                logger.info(f"Usuario UID {uid} eliminado de BD")
                return True
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"Error al eliminar usuario {uid}: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_all_users_from_db(db: Optional[Session] = None) -> List[User]:
        """Obtiene todos los usuarios activos de la BD."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            users = db.query(User).filter(User.deleted_at.is_(None)).all()
            return users
        finally:
            if close_db:
                db.close()

    @staticmethod
    def save_attendance(uid: int, user_id: str, name: str, timestamp: datetime, status: str,
                       db: Optional[Session] = None) -> AttendanceRecord:
        """Guarda un registro de asistencia en la BD."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            record = AttendanceRecord(
                uid=uid,
                user_id=user_id,
                name=name,
                timestamp=timestamp,
                status=status
            )
            db.add(record)
            db.commit()
            logger.debug(f"Registro de asistencia guardado: {user_id} - {timestamp}")
            return record
        except Exception as e:
            db.rollback()
            logger.error(f"Error al guardar asistencia {user_id}: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()

    @staticmethod
    def save_bulk_attendance(records: List[Dict], db: Optional[Session] = None) -> int:
        """Guarda múltiples registros de asistencia. Evita duplicados."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            count = 0
            for record in records:
                timestamp = record.get("timestamp")
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

                existing = db.query(AttendanceRecord).filter(
                    and_(
                        AttendanceRecord.uid == record.get("uid"),
                        AttendanceRecord.timestamp == timestamp,
                        AttendanceRecord.status == record.get("status")
                    )
                ).first()

                if not existing:
                    att = AttendanceRecord(
                        uid=record.get("uid"),
                        user_id=record.get("user_id"),
                        name=record.get("name"),
                        timestamp=timestamp,
                        status=record.get("status")
                    )
                    db.add(att)
                    count += 1

            db.commit()
            logger.info(f"Se guardaron {count} registros de asistencia en BD")
            return count

        except Exception as e:
            db.rollback()
            logger.error(f"Error al guardar asistencias en bulk: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_attendance_by_date_range(start_date: datetime, end_date: datetime,
                                     db: Optional[Session] = None) -> List[AttendanceRecord]:
        """Obtiene registros de asistencia en un rango de fechas."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            records = db.query(AttendanceRecord).filter(
                and_(
                    AttendanceRecord.timestamp >= start_date,
                    AttendanceRecord.timestamp <= end_date
                )
            ).order_by(AttendanceRecord.timestamp.desc()).all()
            return records
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_attendance_by_user(user_id: str, start_date: Optional[datetime] = None,
                              end_date: Optional[datetime] = None,
                              db: Optional[Session] = None) -> List[AttendanceRecord]:
        """Obtiene asistencias de un usuario específico."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            query = db.query(AttendanceRecord).filter(AttendanceRecord.user_id == user_id)

            if start_date and end_date:
                query = query.filter(
                    and_(
                        AttendanceRecord.timestamp >= start_date,
                        AttendanceRecord.timestamp <= end_date
                    )
                )

            return query.order_by(AttendanceRecord.timestamp.desc()).all()
        finally:
            if close_db:
                db.close()
