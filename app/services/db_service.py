"""Servicio de operaciones en base de datos."""
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from app.database.connection import SessionLocal
from app.models.user import User, UserRole
from app.models.attendance import AttendanceRecord
from app.config.logger import get_logger
from app.exceptions import DataValidationError
from app.services.validators import DataValidator
from app.models.device import Device
from app.models.log import Log
from app.models.branch import Branch

logger = get_logger("services.db")

class DBService:
    """Servicio de persistencia en PostgreSQL."""

    @staticmethod
    def save_user(uid: int, user_id: str, name: str, role: str, db: Optional[Session] = None) -> User:
        """Guarda o actualiza un usuario en la BD."""
        # Validar datos antes de guardar
        DataValidator.validate_user(uid, user_id, name, role)

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
                try:
                    existing_user.role = UserRole(role) if role else UserRole.usuario
                except ValueError:
                    raise DataValidationError(f"role inválido: {role}")
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

        except DataValidationError:
            raise
        except ValueError as e:
            db.rollback()
            raise DataValidationError(f"Error al procesar role: {str(e)}")
        except Exception as e:
            db.rollback()
            logger.error(f"Error al guardar usuario {uid}: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()
            
    @staticmethod
    def save_device(nombre: str, ip: str, puerto: int = 4370, sucursal: str = None,
                    ubicacion: str = None, db: Optional[Session] = None) -> Device:
        """Guarda un nuevo reloj biométrico en la BD."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            existing = db.query(Device).filter(Device.ip == ip).first()

            if existing:
                raise DataValidationError(f"Ya existe un reloj registrado con la IP {ip}")

            device = Device(
                name=nombre,
                ip=ip,
                port=puerto,
                location=sucursal,
                description=ubicacion,
                is_active=True,
                status="Desconectado",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            db.add(device)
            db.commit()
            db.refresh(device)

            return device

        except Exception as e:
            db.rollback()
            logger.error(f"Error al guardar reloj {ip}: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_all_devices(db: Optional[Session] = None) -> List[Device]:
        """Obtiene todos los relojes registrados."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            return db.query(Device).order_by(Device.id.asc()).all()
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_device_by_id(device_id: int, db: Optional[Session] = None) -> Optional[Device]:
            """Obtiene un reloj por ID."""
            if db is None:
                db = SessionLocal()
                close_db = True
            else:
                close_db = False

            try:
                return db.query(Device).filter(Device.id == device_id).first()
            finally:
                if close_db:
                    db.close()

    @staticmethod
    def update_device_status(device_id: int, estado: str,
                                ultima_sincronizacion: datetime = None,
                                db: Optional[Session] = None) -> Optional[Device]:
            """Actualiza estado y última conexión de un reloj."""
            if db is None:
                db = SessionLocal()
                close_db = True
            else:
                close_db = False

            try:
                device = db.query(Device).filter(Device.id == device_id).first()

                if not device:
                    return None

                device.status = estado
                if ultima_sincronizacion:
                    device.last_connection = ultima_sincronizacion

                device.updated_at = datetime.utcnow()
                db.commit()
                return device

            except Exception as e:
                db.rollback()
                logger.error(f"Error al actualizar estado del reloj {device_id}: {str(e)}")
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
    def update_user_status(uid: int, status: str, db: Optional[Session] = None) -> Optional[User]:
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            user = db.query(User).filter(User.uid == uid).first()

            if not user:
                return None

            user.status = status
            user.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(user)

            return user

        except Exception as e:
            db.rollback()
            logger.error(f"Error al actualizar estado del usuario {uid}: {str(e)}")
            raise
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

                    # Validar timestamp presente
                    if not timestamp:
                        logger.warning(f"timestamp faltante en registro: {record}")
                        continue

                    if isinstance(timestamp, str):
                        try:
                            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        except ValueError:
                            logger.warning(f"Formato de timestamp inválido: {timestamp}")
                            continue

                    # Validar datos antes de guardar
                    try:
                        DataValidator.validate_attendance(
                            record.get("uid"),
                            record.get("user_id"),
                            record.get("name"),
                            timestamp,
                            record.get("status")
                        )
                    except DataValidationError as e:
                        logger.warning(f"Registro de asistencia inválido descartado: {e}")
                        continue

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

            except DataValidationError:
                raise
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
    def get_attendance_dates_summary(db: Optional[Session] = None) -> List[Dict]:
            """Obtiene las fechas con registros de asistencia y su total."""
            if db is None:
                db = SessionLocal()
                close_db = True
            else:
                close_db = False

            try:
                attendance_date = func.date(AttendanceRecord.timestamp)
                rows = (
                    db.query(
                        attendance_date.label("fecha"),
                        func.count(AttendanceRecord.id).label("total")
                    )
                    .group_by(attendance_date)
                    .order_by(attendance_date.desc())
                    .all()
                )

                return [
                    {
                        "fecha": row.fecha.isoformat() if hasattr(row.fecha, "isoformat") else str(row.fecha),
                        "total": int(row.total),
                    }
                    for row in rows
                ]
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

    @staticmethod
    def update_device(device_id: int, nombre: str = None, ip: str = None,
                      puerto: int = None, sucursal: str = None,
                      ubicacion: str = None, activo: bool = None,
                      db: Optional[Session] = None) -> Optional[Device]:
        """Actualiza datos de un reloj registrado."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            device = db.query(Device).filter(Device.id == device_id).first()

            if not device:
                return None

            if nombre is not None:
                device.name = nombre
            if ip is not None:
                device.ip = ip
            if puerto is not None:
                device.port = puerto
            if sucursal is not None:
                device.location = sucursal
            if ubicacion is not None:
                device.description = ubicacion
            if activo is not None:
                device.is_active = activo

            device.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(device)

            return device

        except Exception as e:
            db.rollback()
            logger.error(f"Error al actualizar reloj {device_id}: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()

    @staticmethod
    def delete_device(device_id: int, db: Optional[Session] = None) -> bool:
        """Inactiva un reloj registrado en lugar de eliminarlo."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            device = db.query(Device).filter(Device.id == device_id).first()

            if not device:
                return False

            device.is_active = False
            device.status = "Inactivo"
            device.updated_at = datetime.utcnow()

            db.commit()

            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Error al inactivar reloj {device_id}: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()

    @staticmethod
    def activate_device(device_id: int, db: Optional[Session] = None) -> bool:
        """Reactiva un reloj previamente inactivado."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            device = db.query(Device).filter(Device.id == device_id).first()

            if not device:
                return False

            device.is_active = True
            device.status = "Desconectado"
            device.updated_at = datetime.utcnow()

            db.commit()

            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Error al activar reloj {device_id}: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()

    @staticmethod
    def create_log(accion: str, detalle: str, db: Optional[Session] = None) -> Log:
        """Crea un registro de auditoría."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            log = Log(
                accion=accion,
                detalle=detalle,
                created_at=datetime.utcnow()
            )

            db.add(log)
            db.commit()
            db.refresh(log)

            return log

        except Exception as e:
            db.rollback()
            logger.error(f"Error al crear log: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_logs(limit: int = 100, db: Optional[Session] = None) -> List[Log]:
        """Obtiene los últimos registros de auditoría."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            return (
                db.query(Log)
                .order_by(Log.created_at.desc())
                .limit(limit)
                .all()
            )
        finally:
            if close_db:
                db.close()

    @staticmethod
    def create_branch(
        name: str,
        address: str = None,
        is_active: bool = True,
        status: str = "Activo",
        db: Optional[Session] = None
    ) -> Branch:
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            existing = db.query(Branch).filter(Branch.name == name).first()

            if existing:
                raise DataValidationError(f"Ya existe una sucursal llamada {name}")

            if status not in ("Activo", "Inactivo", "Baja"):
                status = "Activo" if is_active else "Inactivo"

            branch = Branch(
                name=name,
                address=address,
                is_active=status == "Activo",
                status=status,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            db.add(branch)
            db.commit()
            db.refresh(branch)

            return branch

        except Exception as e:
            db.rollback()
            logger.error(f"Error al crear sucursal {name}: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()


    @staticmethod
    def get_all_branches(db: Optional[Session] = None) -> List[Branch]:
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            return db.query(Branch).order_by(Branch.id.asc()).all()
        finally:
            if close_db:
                db.close()

    @staticmethod
    def update_user_profile(
        uid: int,
        role: str = None,
        sucursal: str = None,
        email: str = None,
        db: Optional[Session] = None
    ) -> Optional[User]:
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            user = db.query(User).filter(User.uid == uid).first()

            if not user:
                return None

            if role is not None:
                user.role = UserRole(role) if role else UserRole.usuario

            if sucursal is not None:
                user.sucursal = sucursal

            if email is not None:
                user.email = email

            user.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(user)

            return user

        except Exception as e:
            db.rollback()
            logger.error(f"Error al actualizar perfil del usuario {uid}: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()

    @staticmethod
    def update_branch(
        branch_id: int,
        name: str = None,
        address: str = None,
        is_active: bool = None,
        status: str = None,
        db: Optional[Session] = None
    ) -> Optional[Branch]:
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            branch = db.query(Branch).filter(Branch.id == branch_id).first()

            if not branch:
                return None

            if name is not None:
                branch.name = name

            if address is not None:
                branch.address = address

            if status is not None:
                if status not in ("Activo", "Inactivo", "Baja"):
                    status = "Activo" if is_active else "Inactivo"

                branch.status = status
                branch.is_active = status == "Activo"

            elif is_active is not None:
                branch.is_active = is_active
                branch.status = "Activo" if is_active else "Inactivo"

            branch.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(branch)

            return branch

        except Exception as e:
            db.rollback()
            logger.error(f"Error al actualizar sucursal {branch_id}: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()
            
    
    
    
    