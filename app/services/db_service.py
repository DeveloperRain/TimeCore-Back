"""Servicio de operaciones en base de datos."""
from typing import List, Dict, Optional
import json
import re
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import and_, func, or_

from app.database.connection import SessionLocal
from app.models.user import User, UserRole
from app.models.attendance import AttendanceRecord
from app.models.device import Device
from app.models.log import Log
from app.models.branch import Branch
from app.models.payroll_incident import PayrollIncident
from app.config.logger import get_logger
from app.exceptions import DataValidationError
from app.services.validators import DataValidator

logger = get_logger("services.db")



def _parse_assignment_filter(value: str):
    """Devuelve (device_id, user_id) para claves como '6:23'."""
    raw = str(value or "").strip()
    if not raw or ":" not in raw:
        return None

    device_raw, user_id = raw.split(":", 1)
    try:
        device_id = int(device_raw)
    except (TypeError, ValueError):
        return None

    user_id = user_id.strip()
    if not user_id:
        return None

    return device_id, user_id


class DBService:
    """Servicio de persistencia en PostgreSQL."""

    # =========================
    # HELPERS INTERNOS
    # =========================

    @staticmethod
    def _get_branch_by_name(db: Session, sucursal: Optional[str]) -> Optional[Branch]:
        if not sucursal:
            return None

        return (
            db.query(Branch)
            .filter(func.lower(func.trim(Branch.name)) == sucursal.strip().lower())
            .first()
        )

    @staticmethod
    def _resolve_branch_id(
        db: Session,
        branch_id: Optional[int] = None,
        sucursal: Optional[str] = None,
    ) -> Optional[int]:
        if branch_id is not None:
            branch = db.query(Branch).filter(Branch.id == branch_id).first()
            return branch.id if branch else None

        branch = DBService._get_branch_by_name(db, sucursal)
        return branch.id if branch else None

    @staticmethod
    def _resolve_user_branch_id(
        db: Session,
        uid: Optional[int],
        user_id: Optional[str],
        device_id: Optional[int] = None,
    ) -> Optional[int]:
        query = db.query(User)
        if device_id is not None:
            query = query.filter(User.device_id == device_id)

        user = None

        if uid is not None:
            user = query.filter(User.uid == uid).first()

        if not user and user_id:
            user = query.filter(User.user_id == user_id).first()

        return user.branch_id if user else None

    # =========================
    # USUARIOS
    # =========================

    @staticmethod
    def save_user(
        uid: int,
        user_id: str,
        name: str,
        role: str,
        sucursal: Optional[str] = None,
        branch_id: Optional[int] = None,
        device_id: Optional[int] = None,
        empresa: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> User:
        """Guarda o actualiza un usuario en la BD."""
        DataValidator.validate_user(uid, user_id, name, role)

        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            resolved_branch_id = DBService._resolve_branch_id(
                db=db,
                branch_id=branch_id,
                sucursal=sucursal,
            )

            existing_query = db.query(User).filter(User.uid == uid)
            if device_id is not None:
                existing_query = existing_query.filter(User.device_id == device_id)
            existing_user = existing_query.first()

            # Adopta registros antiguos sin device_id durante la primera sincronización.
            if not existing_user and device_id is not None:
                legacy_user = (
                    db.query(User)
                    .filter(User.device_id.is_(None))
                    .filter(User.uid == uid)
                    .filter(User.user_id == user_id)
                    .first()
                )
                if legacy_user:
                    legacy_user.device_id = device_id
                    existing_user = legacy_user

            if existing_user:
                existing_user.user_id = user_id
                existing_user.name = name

                try:
                    existing_user.role = UserRole(role) if role else UserRole.usuario
                except ValueError:
                    raise DataValidationError(f"role inválido: {role}")

                if sucursal is not None:
                    existing_user.sucursal = sucursal

                if resolved_branch_id is not None:
                    existing_user.branch_id = resolved_branch_id

                if device_id is not None:
                    existing_user.device_id = device_id

                if empresa is not None:
                    existing_user.empresa = empresa

                # Si el empleado vuelve a aparecer en el reloj, se reactiva
                # sin perder su historial ni su perfil local.
                existing_user.status = "Activo"
                existing_user.deleted_at = None
                existing_user.updated_at = datetime.utcnow()

                db.commit()
                db.refresh(existing_user)

                logger.info(f"Usuario UID {uid} actualizado en BD")
                return existing_user

            new_user = User(
                uid=uid,
                user_id=user_id,
                name=name,
                role=UserRole(role) if role else UserRole.usuario,
                sucursal=sucursal,
                branch_id=resolved_branch_id,
                device_id=device_id,
                empresa=empresa,
                status="Activo",
                deleted_at=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            db.add(new_user)
            db.commit()
            db.refresh(new_user)

            logger.info(f"Usuario UID {uid} guardado en BD")
            return new_user

        except DataValidationError:
            db.rollback()
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
    def get_all_users_from_db(db: Optional[Session] = None) -> List[User]:
        """Obtiene todos los usuarios activos de la BD."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            return (
                db.query(User)
                .order_by(User.name.asc())
                .all()
            )
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_users_by_branch(branch_id: int, db: Optional[Session] = None) -> List[User]:
        """Obtiene empleados de una sucursal usando branch_id real."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            return (
                db.query(User)
                .filter(User.branch_id == branch_id)
                .order_by(User.name.asc())
                .all()
            )
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_users_paginated(
        page: int = 1,
        limit: int = 50,
        branch_id: Optional[int] = None,
        search: Optional[str] = None,
        status: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Dict:
        """Obtiene empleados paginados y filtrados directamente en PostgreSQL."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            query = db.query(User)

            if branch_id is not None:
                query = query.filter(User.branch_id == branch_id)

            if status:
                query = query.filter(func.lower(User.status) == status.lower())

            if search and search.strip():
                term = f"%{search.strip()}%"
                query = query.filter(
                    or_(
                        User.name.ilike(term),
                        User.user_id.ilike(term),
                        User.area.ilike(term),
                        User.empresa.ilike(term),
                        User.email.ilike(term),
                        User.sucursal.ilike(term),
                    )
                )

            total = query.count()
            items = (
                query.order_by(User.name.asc())
                .offset((page - 1) * limit)
                .limit(limit)
                .all()
            )

            return {"items": items, "total": total}
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_user_by_id(user_id: int, db: Optional[Session] = None) -> Optional[User]:
        """Obtiene un empleado por la PK interna de PostgreSQL."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            return (
                db.query(User)
                .filter(User.id == user_id)
                .first()
            )
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_next_uid_for_device(
        device_id: int,
        db: Optional[Session] = None,
    ) -> int:
        """Obtiene la siguiente UID local disponible para un reloj."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            max_uid = (
                db.query(func.max(User.uid))
                .filter(User.device_id == device_id)
                .scalar()
            )
            return int(max_uid or 0) + 1
        finally:
            if close_db:
                db.close()

    @staticmethod
    def create_user_assignment_copy(
        source_user_id: int,
        target_device_id: int,
        uid: int,
        user_id: str,
        db: Optional[Session] = None,
    ) -> User:
        """Crea una asignacion independiente en otro reloj.

        La fila original no se modifica y sus asistencias historicas conservan
        el UID y device_id de origen.
        """
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            source = db.query(User).filter(User.id == source_user_id).first()
            if not source:
                raise ValueError("Empleado de origen no encontrado")

            target_device = (
                db.query(Device)
                .filter(Device.id == target_device_id)
                .first()
            )
            if not target_device:
                raise ValueError("Reloj destino no encontrado")

            if source.device_id == target_device_id:
                raise ValueError(
                    "El empleado ya pertenece a ese reloj. Selecciona otro reloj destino"
                )

            existing = (
                db.query(User)
                .filter(User.device_id == target_device_id)
                .filter(User.uid == uid)
                .first()
            )
            if existing:
                raise ValueError(
                    f"La UID {uid} ya esta registrada en el reloj destino"
                )

            target_branch = None
            if target_device.branch_id is not None:
                target_branch = (
                    db.query(Branch)
                    .filter(Branch.id == target_device.branch_id)
                    .first()
                )

            new_user = User(
                uid=int(uid),
                user_id=str(user_id),
                name=source.name,
                role=source.role,
                device_id=target_device.id,
                branch_id=target_device.branch_id,
                sucursal=(
                    target_branch.name
                    if target_branch
                    else target_device.location
                ),
                email=source.email,
                area=source.area,
                empresa=target_device.empresa,
                status="Activo",
                deleted_at=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            return new_user
        except Exception:
            db.rollback()
            raise
        finally:
            if close_db:
                db.close()

    @staticmethod
    def update_user_status_by_id(
        user_id: int,
        status: str,
        db: Optional[Session] = None,
    ) -> Optional[User]:
        """Actualiza el estado usando la PK interna, no el UID del reloj."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return None

            user.status = status
            user.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(user)
            return user
        except Exception as e:
            db.rollback()
            logger.error(f"Error al actualizar estado del usuario ID {user_id}: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()

    @staticmethod
    def update_user_profile_by_id(
        user_id: int,
        role: str = None,
        sucursal: str = None,
        email: str = None,
        area: str = None,
        empresa: str = None,
        branch_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> Optional[User]:
        """Actualiza el perfil usando la PK interna de PostgreSQL."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return None

            if role is not None:
                user.role = UserRole(role) if role else UserRole.usuario

            resolved_branch_id = DBService._resolve_branch_id(
                db=db, branch_id=branch_id, sucursal=sucursal
            )

            if branch_id is not None:
                branch = db.query(Branch).filter(Branch.id == branch_id).first()
                if branch:
                    user.branch_id = branch.id
                    user.sucursal = branch.name
            elif sucursal is not None:
                user.sucursal = sucursal
                if resolved_branch_id is not None:
                    user.branch_id = resolved_branch_id

            if email is not None:
                user.email = email
            if area is not None:
                user.area = area
            if empresa is not None:
                user.empresa = empresa

            user.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(user)
            return user
        except Exception as e:
            db.rollback()
            logger.error(f"Error al actualizar perfil del usuario ID {user_id}: {str(e)}")
            raise
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
    def update_user_profile(
        uid: int,
        role: str = None,
        sucursal: str = None,
        email: str = None,
        area: str = None,
        empresa: str = None,
        branch_id: Optional[int] = None,
        db: Optional[Session] = None,
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

            resolved_branch_id = DBService._resolve_branch_id(
                db=db,
                branch_id=branch_id,
                sucursal=sucursal,
            )

            if branch_id is not None:
                branch = db.query(Branch).filter(Branch.id == branch_id).first()

                if branch:
                    user.branch_id = branch.id
                    user.sucursal = branch.name

            elif sucursal is not None:
                user.sucursal = sucursal

                if resolved_branch_id is not None:
                    user.branch_id = resolved_branch_id

            if email is not None:
                user.email = email

            if area is not None:
                user.area = area

            if empresa is not None:
                user.empresa = empresa

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
    def mark_missing_device_users(
        device_id: int,
        present_uids: List[int],
        db: Optional[Session] = None,
    ) -> int:
        """Marca como inactivos a los empleados que ya no están en el reloj.

        No elimina filas ni asistencias. Si el empleado vuelve a aparecer en una
        sincronización posterior, save_user() lo reactiva automáticamente.
        """
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            normalized_uids = [int(uid) for uid in present_uids]
            query = db.query(User).filter(User.device_id == device_id)

            if normalized_uids:
                query = query.filter(~User.uid.in_(normalized_uids))

            missing_users = query.all()
            now = datetime.utcnow()

            for user in missing_users:
                user.status = "Inactivo"
                user.deleted_at = None
                user.updated_at = now

            db.commit()

            if missing_users:
                logger.info(
                    "Se marcaron %s empleados como inactivos para el reloj %s",
                    len(missing_users),
                    device_id,
                )

            return len(missing_users)
        except Exception as e:
            db.rollback()
            logger.error(
                "Error al conservar empleados ausentes del reloj %s: %s",
                device_id,
                str(e),
            )
            raise
        finally:
            if close_db:
                db.close()

    @staticmethod
    def delete_user(
        uid: int,
        device_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> bool:
        """Conserva al empleado en BD y sólo lo marca como inactivo.

        Las asistencias históricas permanecen intactas.
        """
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            query = db.query(User).filter(User.uid == uid)
            if device_id is not None:
                query = query.filter(User.device_id == device_id)

            user = query.first()

            if not user:
                return False

            user.status = "Inactivo"
            user.deleted_at = None
            user.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(user)

            logger.info(
                "Usuario UID %s del reloj %s conservado en BD como inactivo",
                uid,
                device_id,
            )
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Error al conservar usuario {uid}: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()

    # =========================
    # RELOJES / DEVICES
    # =========================

    @staticmethod
    def save_device(
        nombre: str,
        ip: str,
        puerto: int = 4370,
        password: str = "",
        sucursal: str = None,
        ubicacion: str = None,
        empresa: str = "FISMAN",
        branch_id: Optional[int] = None,
        auto_sync_enabled: bool = True,
        sync_interval_minutes: int = 4,
        db: Optional[Session] = None,
    ) -> Device:
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

            resolved_branch_id = DBService._resolve_branch_id(
                db=db,
                branch_id=branch_id,
                sucursal=sucursal,
            )

            if branch_id is not None:
                branch = db.query(Branch).filter(Branch.id == branch_id).first()
                if branch:
                    sucursal = branch.name

            device = Device(
                name=nombre,
                ip=ip,
                port=puerto,
                password=password,
                branch_id=resolved_branch_id,
                location=sucursal,
                description=ubicacion,
                empresa=empresa,
                is_active=True,
                auto_sync_enabled=bool(auto_sync_enabled),
                sync_interval_minutes=max(1, min(int(sync_interval_minutes or 4), 60)),
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
    def get_devices_by_branch(branch_id: int, db: Optional[Session] = None) -> List[Device]:
        """Obtiene relojes de una sucursal usando branch_id real."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            return (
                db.query(Device)
                .filter(Device.branch_id == branch_id)
                .order_by(Device.id.asc())
                .all()
            )
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
    def update_device(
        device_id: int,
        nombre: str = None,
        ip: str = None,
        puerto: int = None,
        password: str = None,
        sucursal: str = None,
        ubicacion: str = None,
        empresa: str = None,
        activo: bool = None,
        branch_id: Optional[int] = None,
        auto_sync_enabled: Optional[bool] = None,
        sync_interval_minutes: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> Optional[Device]:
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

            if password is not None:
                if not str(password).strip():
                    raise DataValidationError("La contraseña del reloj no puede quedar vacía")
                device.password = str(password).strip()

            if branch_id is not None:
                branch = db.query(Branch).filter(Branch.id == branch_id).first()

                if branch:
                    device.branch_id = branch.id
                    device.location = branch.name

            elif sucursal is not None:
                device.location = sucursal

                resolved_branch_id = DBService._resolve_branch_id(
                    db=db,
                    sucursal=sucursal,
                )

                if resolved_branch_id is not None:
                    device.branch_id = resolved_branch_id

            if ubicacion is not None:
                device.description = ubicacion

            if empresa is not None:
                device.empresa = empresa

            if auto_sync_enabled is not None:
                device.auto_sync_enabled = bool(auto_sync_enabled)

            if sync_interval_minutes is not None:
                interval = int(sync_interval_minutes)
                if interval < 1 or interval > 60:
                    raise DataValidationError("El intervalo debe estar entre 1 y 60 minutos")
                device.sync_interval_minutes = interval

            if activo is not None:
                device.is_active = activo

                if activo and device.status == "Inactivo":
                    device.status = "Desconectado"

                if not activo:
                    device.status = "Inactivo"

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
    def update_device_status(
        device_id: int,
        estado: str,
        ultima_sincronizacion: datetime = None,
        db: Optional[Session] = None,
    ) -> Optional[Device]:
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
            db.refresh(device)

            return device

        except Exception as e:
            db.rollback()
            logger.error(f"Error al actualizar estado del reloj {device_id}: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()

    @staticmethod
    def update_device_sync_status(
        device_id: int,
        estado: str = "Conectado",
        synced_at: datetime = None,
        db: Optional[Session] = None,
    ) -> Optional[Device]:
        """Actualiza el estado y la última sincronización real del reloj."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            device = db.query(Device).filter(Device.id == device_id).first()
            if not device:
                return None

            now = synced_at or datetime.utcnow()
            device.status = estado
            device.last_connection = now
            device.last_sync_at = now
            device.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(device)
            return device
        except Exception as e:
            db.rollback()
            logger.error(f"Error al actualizar sincronización del reloj {device_id}: {str(e)}")
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

    # =========================
    # ASISTENCIAS
    # =========================

    @staticmethod
    def save_attendance(
        uid: int,
        user_id: str,
        name: str,
        timestamp: datetime,
        status: str,
        branch_id: Optional[int] = None,
        device_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> AttendanceRecord:
        """Guarda un registro de asistencia en la BD."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            resolved_branch_id = branch_id

            if resolved_branch_id is None:
                resolved_branch_id = DBService._resolve_user_branch_id(
                    db=db,
                    uid=uid,
                    user_id=user_id,
                    device_id=device_id,
                )

            record = AttendanceRecord(
                uid=uid,
                user_id=user_id,
                name=name,
                branch_id=resolved_branch_id,
                device_id=device_id,
                timestamp=timestamp,
                status=status,
            )

            db.add(record)
            db.commit()
            db.refresh(record)

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
    def save_bulk_attendance(
        records: List[Dict],
        branch_id: Optional[int] = None,
        device_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> int:
        """Guarda múltiples asistencias sin mezclar relojes.

        La identidad de una marcación se determina por:
        ``device_id + uid/user_id + timestamp + status``. También normaliza UID,
        recupera nombre/UID desde la asignación local cuando el reloj no los
        devuelve y registra un resumen útil de descartes y duplicados.
        """
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        inserted = 0
        duplicates = 0
        invalid = 0

        try:
            for raw_record in records:
                record = dict(raw_record or {})
                timestamp = record.get("timestamp")

                if not timestamp:
                    invalid += 1
                    logger.warning("timestamp faltante en registro: %s", record)
                    continue

                if isinstance(timestamp, str):
                    try:
                        timestamp = datetime.fromisoformat(
                            timestamp.replace("Z", "+00:00")
                        )
                    except ValueError:
                        invalid += 1
                        logger.warning("Formato de timestamp inválido: %s", timestamp)
                        continue

                # PostgreSQL usa timestamp sin zona; se conserva la hora local
                # reportada por el reloj y se elimina tzinfo si viniera presente.
                if getattr(timestamp, "tzinfo", None) is not None:
                    timestamp = timestamp.replace(tzinfo=None)

                record_device_id = record.get("device_id", device_id)
                record_branch_id = record.get("branch_id", branch_id)
                user_id = str(record.get("user_id") or "").strip()
                uid = record.get("uid")

                try:
                    uid = int(uid) if uid not in (None, "") else None
                except (TypeError, ValueError):
                    uid = None

                linked_user = None
                if record_device_id is not None:
                    user_query = db.query(User).filter(
                        User.device_id == record_device_id
                    )
                    if user_id:
                        linked_user = user_query.filter(User.user_id == user_id).first()
                    if linked_user is None and uid is not None:
                        linked_user = user_query.filter(User.uid == uid).first()

                if linked_user is not None:
                    uid = int(linked_user.uid)
                    user_id = str(linked_user.user_id)
                    name = str(record.get("name") or linked_user.name or "").strip()
                    if not name or name.lower() == "desconocido":
                        name = linked_user.name
                    if record_branch_id is None:
                        record_branch_id = linked_user.branch_id
                else:
                    name = str(record.get("name") or "").strip()

                status = str(record.get("status") or "check_in").strip()

                try:
                    DataValidator.validate_attendance(
                        uid,
                        user_id,
                        name,
                        timestamp,
                        status,
                    )
                except (DataValidationError, TypeError, ValueError) as e:
                    invalid += 1
                    logger.warning(
                        "Registro de asistencia inválido descartado: %s | %s",
                        e,
                        record,
                    )
                    continue

                if record_branch_id is None:
                    record_branch_id = DBService._resolve_user_branch_id(
                        db=db,
                        uid=uid,
                        user_id=user_id,
                        device_id=record_device_id,
                    )

                identity_filters = [
                    AttendanceRecord.device_id == record_device_id,
                    AttendanceRecord.timestamp == timestamp,
                    AttendanceRecord.status == status,
                ]
                if uid is not None:
                    identity_filters.append(AttendanceRecord.uid == uid)
                else:
                    identity_filters.append(AttendanceRecord.user_id == user_id)

                existing = (
                    db.query(AttendanceRecord)
                    .filter(and_(*identity_filters))
                    .first()
                )

                if existing:
                    duplicates += 1
                    continue

                db.add(
                    AttendanceRecord(
                        uid=uid,
                        user_id=user_id,
                        name=name or f"Usuario {user_id}",
                        branch_id=record_branch_id,
                        device_id=record_device_id,
                        timestamp=timestamp,
                        status=status,
                    )
                )
                inserted += 1

            db.commit()

            logger.info(
                "Asistencias procesadas: recibidas=%s, nuevas=%s, duplicadas=%s, inválidas=%s, device_id=%s",
                len(records),
                inserted,
                duplicates,
                invalid,
                device_id,
            )
            return inserted

        except Exception as e:
            db.rollback()
            logger.error("Error al guardar asistencias en bulk: %s", e)
            raise
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_attendance_paginated(
        page: int = 1,
        limit: int = 50,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        branch_id: Optional[int] = None,
        user_ids: Optional[List[str]] = None,
        db: Optional[Session] = None,
    ) -> Dict:
        """Obtiene asistencias paginadas sin cargar toda la tabla en memoria."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            query = db.query(AttendanceRecord)

            if start_date is not None:
                query = query.filter(AttendanceRecord.timestamp >= start_date)
            if end_date is not None:
                query = query.filter(AttendanceRecord.timestamp <= end_date)
            if branch_id is not None:
                query = query.filter(AttendanceRecord.branch_id == branch_id)
            if user_ids:
                assignment_filters = []
                legacy_user_ids = []

                for value in user_ids:
                    raw = str(value or "").strip()
                    if not raw:
                        continue

                    parsed = _parse_assignment_filter(raw)
                    if parsed:
                        selected_device_id, selected_user_id = parsed
                        assignment_filters.append(
                            and_(
                                AttendanceRecord.device_id == selected_device_id,
                                AttendanceRecord.user_id == selected_user_id,
                            )
                        )
                    else:
                        legacy_user_ids.append(raw)

                filters = list(assignment_filters)
                if legacy_user_ids:
                    filters.append(
                        AttendanceRecord.user_id.in_(legacy_user_ids)
                    )

                if filters:
                    query = query.filter(or_(*filters))

            total = query.count()
            items = (
                query.order_by(AttendanceRecord.timestamp.desc())
                .offset((page - 1) * limit)
                .limit(limit)
                .all()
            )

            return {"items": items, "total": total}
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_attendance_by_date_range(
        start_date: datetime,
        end_date: datetime,
        db: Optional[Session] = None,
    ) -> List[AttendanceRecord]:
        """Obtiene registros de asistencia en un rango de fechas."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            return (
                db.query(AttendanceRecord)
                .filter(
                    and_(
                        AttendanceRecord.timestamp >= start_date,
                        AttendanceRecord.timestamp <= end_date,
                    )
                )
                .order_by(AttendanceRecord.timestamp.desc())
                .all()
            )
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_attendance_by_branch(
        branch_id: int,
        db: Optional[Session] = None,
    ) -> List[AttendanceRecord]:
        """Obtiene asistencias de una sucursal usando branch_id real."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            return (
                db.query(AttendanceRecord)
                .filter(AttendanceRecord.branch_id == branch_id)
                .order_by(AttendanceRecord.timestamp.desc())
                .all()
            )
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_attendance_by_user(
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        db: Optional[Session] = None,
    ) -> List[AttendanceRecord]:
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
                        AttendanceRecord.timestamp <= end_date,
                    )
                )

            return query.order_by(AttendanceRecord.timestamp.desc()).all()

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
                    func.count(AttendanceRecord.id).label("total"),
                )
                .group_by(attendance_date)
                .order_by(attendance_date.desc())
                .all()
            )

            return [
                {
                    "fecha": row.fecha.isoformat()
                    if hasattr(row.fecha, "isoformat")
                    else str(row.fecha),
                    "total": int(row.total),
                }
                for row in rows
            ]

        finally:
            if close_db:
                db.close()


    # =========================
    # PRENÓMINA / INCIDENCIAS
    # =========================

    @staticmethod
    def get_payroll_incidents_by_range(
        start_date,
        end_date,
        branch_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> List[PayrollIncident]:
        """Obtiene incidencias distinguiendo cada asignación por reloj + usuario."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            query = (
                db.query(PayrollIncident)
                .filter(
                    or_(
                        and_(
                            PayrollIncident.fecha >= start_date,
                            PayrollIncident.fecha <= end_date,
                        ),
                        and_(
                            PayrollIncident.source_fecha.isnot(None),
                            PayrollIncident.source_fecha >= start_date,
                            PayrollIncident.source_fecha <= end_date,
                        ),
                    )
                )
            )

            if branch_id is not None:
                branch_device_ids = (
                    db.query(Device.id)
                    .filter(Device.branch_id == branch_id)
                    .subquery()
                )
                branch_user_ids = (
                    db.query(User.user_id)
                    .filter(User.branch_id == branch_id)
                    .subquery()
                )

                query = query.filter(
                    or_(
                        PayrollIncident.device_id.in_(branch_device_ids),
                        and_(
                            PayrollIncident.device_id.is_(None),
                            PayrollIncident.user_id.in_(branch_user_ids),
                        ),
                    )
                )

            return query.order_by(
                PayrollIncident.fecha.asc(),
                PayrollIncident.hora.asc(),
                PayrollIncident.device_id.asc().nullsfirst(),
                PayrollIncident.user_id.asc(),
                PayrollIncident.id.asc(),
            ).all()

        finally:
            if close_db:
                db.close()

    @staticmethod
    def save_payroll_incident(
        user_id: str,
        fecha,
        hora,
        incidencia: str,
        descripcion: str = None,
        color: str = "#BAE6FD",
        incident_id: Optional[int] = None,
        device_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> PayrollIncident:
        """
        Crea o actualiza una incidencia para una asignación concreta.

        La identidad del empleado es device_id + user_id. Cambiar la fecha de
        la incidencia no mueve ni copia registros biométricos.
        """
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            clean_user_id = str(user_id).strip()
            clean_incidencia = str(incidencia or "").strip()
            clean_descripcion = (
                str(descripcion).strip() if descripcion is not None else None
            )
            clean_color = str(color or "#BAE6FD").strip().upper()

            if not re.fullmatch(r"#[0-9A-F]{6}", clean_color):
                raise DataValidationError(
                    "El color debe estar en formato hexadecimal, por ejemplo #BAE6FD"
                )
            if not clean_user_id:
                raise DataValidationError("El empleado es obligatorio")
            if not clean_incidencia:
                raise DataValidationError("La incidencia es obligatoria")
            if device_id is None:
                raise DataValidationError(
                    "El reloj del empleado es obligatorio para guardar la incidencia"
                )

            device = db.query(Device).filter(Device.id == device_id).first()
            if not device:
                raise DataValidationError("El reloj seleccionado no existe")

            user = (
                db.query(User)
                .filter(
                    User.device_id == device_id,
                    User.user_id == clean_user_id,
                )
                .first()
            )
            if not user:
                raise DataValidationError(
                    "No existe ese empleado en el reloj seleccionado"
                )

            if incident_id is not None:
                incident = (
                    db.query(PayrollIncident)
                    .filter(PayrollIncident.id == incident_id)
                    .first()
                )
                if not incident:
                    raise DataValidationError(
                        "La incidencia que intentas editar ya no existe"
                    )

                incident.uid = user.uid
                incident.device_id = device_id
                incident.user_id = clean_user_id
                incident.fecha = fecha
                incident.hora = hora
                incident.incidencia = clean_incidencia
                incident.descripcion = clean_descripcion
                incident.color = clean_color

                # Sólo cambia la incidencia elegida por su id. Las demás
                # incidencias del mismo día y hora permanecen intactas.
                incident.source_fecha = fecha
                incident.source_hora = hora
                incident.moved_attendance = None
                incident.updated_at = datetime.utcnow()

                db.commit()
                db.refresh(incident)
                return incident

            # Sin id siempre se inserta una incidencia nueva. Ya no se busca ni
            # se reemplaza otra por device_id + user_id + fecha + hora.
            incident = PayrollIncident(
                uid=user.uid,
                device_id=device_id,
                user_id=clean_user_id,
                fecha=fecha,
                hora=hora,
                incidencia=clean_incidencia,
                descripcion=clean_descripcion,
                color=clean_color,
                source_fecha=fecha,
                source_hora=hora,
                moved_attendance=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            db.add(incident)
            db.commit()
            db.refresh(incident)
            return incident

        except Exception as e:
            db.rollback()
            logger.error(
                "Error al guardar incidencia de prenómina device_id=%s user_id=%s: %s",
                device_id,
                user_id,
                str(e),
            )
            raise
        finally:
            if close_db:
                db.close()

    @staticmethod
    def delete_payroll_incident(
        incident_id: int,
        db: Optional[Session] = None,
    ) -> bool:
        """Elimina una incidencia de prenómina."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            incident = db.query(PayrollIncident).filter(PayrollIncident.id == incident_id).first()

            if not incident:
                return False

            db.delete(incident)
            db.commit()

            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Error al borrar incidencia de prenómina {incident_id}: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()

    # =========================
    # SUCURSALES
    # =========================

    @staticmethod
    def create_branch(
        name: str,
        address: str = None,
        is_active: bool = True,
        status: str = "Activo",
        db: Optional[Session] = None,
    ) -> Branch:
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            existing = db.query(Branch).filter(
                func.lower(func.trim(Branch.name)) == name.strip().lower()
            ).first()

            if existing:
                raise DataValidationError(f"Ya existe una sucursal llamada {name}")

            if status not in ("Activo", "Inactivo"):
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
    def get_branch_by_id(branch_id: int, db: Optional[Session] = None) -> Optional[Branch]:
        """Obtiene una sucursal por ID."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            return db.query(Branch).filter(Branch.id == branch_id).first()
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
        db: Optional[Session] = None,
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

            old_name = branch.name

            if name is not None:
                branch.name = name

            if address is not None:
                branch.address = address

            if status is not None:
                if status not in ("Activo", "Inactivo"):
                    status = "Activo" if is_active else "Inactivo"

                branch.status = status
                branch.is_active = status == "Activo"

            elif is_active is not None:
                branch.is_active = is_active
                branch.status = "Activo" if is_active else "Inactivo"

            branch.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(branch)

            if name is not None and name != old_name:
                db.query(User).filter(User.branch_id == branch_id).update(
                    {User.sucursal: branch.name},
                    synchronize_session=False,
                )

                db.query(Device).filter(Device.branch_id == branch_id).update(
                    {Device.location: branch.name},
                    synchronize_session=False,
                )

                db.commit()

            return branch

        except Exception as e:
            db.rollback()
            logger.error(f"Error al actualizar sucursal {branch_id}: {str(e)}")
            raise
        finally:
            if close_db:
                db.close()

    # =========================
    # LOGS
    # =========================

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
                created_at=datetime.utcnow(),
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
