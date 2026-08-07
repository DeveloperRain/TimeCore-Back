"""Servicio de operaciones en base de datos."""
from typing import List, Dict, Optional
import json
import re
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import and_, func, or_

from app.database.connection import SessionLocal
from app.models.user import User, UserRole
from app.models.attendance import AttendanceRecord as AttendanceModel
from app.models.device import Device
from app.models.log import Log
from app.models.branch import Branch
from app.models.payroll_incident import PayrollIncident
from app.config.logger import get_logger
from app.exceptions import DataValidationError
from app.services.validators import DataValidator

logger = get_logger("services.db")



def _parse_assignment_filter(value: str):
    """
    Interpreta una clave de asignación compuesta por el identificador del dispositivo y el identificador del usuario.

    :param value: Clave de asignación que se debe interpretar.
    :type value: str
    :return: Tupla con el identificador del dispositivo y del usuario, o ``None`` si la clave no es válida.
    :rtype: tuple[int, str] or None
    """
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
        """
        Busca una sucursal mediante su nombre normalizado.

        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session
        :param sucursal: Nombre opcional de la sucursal.
        :type sucursal: str or None
        :return: Sucursal encontrada o ``None`` si no existe una coincidencia.
        :rtype: Branch or None
        """
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
        """
        Resuelve el identificador de una sucursal a partir de su ID o de su nombre.

        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session
        :param branch_id: Identificador opcional de la sucursal.
        :type branch_id: int or None
        :param sucursal: Nombre opcional de la sucursal.
        :type sucursal: str or None
        :return: Identificador de la sucursal encontrada o ``None``.
        :rtype: int or None
        """
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
        """
        Obtiene el identificador de sucursal asociado a un usuario.

        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session
        :param uid: UID del usuario en el dispositivo.
        :type uid: int or None
        :param user_id: Identificador del usuario.
        :type user_id: str or None
        :param device_id: Identificador opcional del dispositivo.
        :type device_id: int or None
        :return: Identificador de sucursal del usuario o ``None``.
        :rtype: int or None
        """
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
        """
        Guarda un usuario nuevo o actualiza su asignación existente en la base de datos.

        :param uid: UID del usuario en el dispositivo.
        :type uid: int
        :param user_id: Identificador del usuario.
        :type user_id: str
        :param name: Nombre del usuario o de la sucursal, según la operación.
        :type name: str
        :param role: Rol del usuario.
        :type role: str
        :param sucursal: Nombre opcional de la sucursal.
        :type sucursal: str or None
        :param branch_id: Identificador opcional de la sucursal.
        :type branch_id: int or None
        :param device_id: Identificador opcional del dispositivo.
        :type device_id: int or None
        :param empresa: Empresa asociada.
        :type empresa: str or None
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Usuario creado o actualizado.
        :rtype: User
        :raises DataValidationError: Si los datos del usuario o el rol no son válidos.
        :raises Exception: Si ocurre un error durante la operación de persistencia.
        """
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
        """
        Obtiene todos los usuarios registrados en la base de datos.

        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Lista de usuarios registrados.
        :rtype: list[User]
        """
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
        """
        Obtiene los usuarios asociados a una sucursal.

        :param branch_id: Identificador opcional de la sucursal.
        :type branch_id: int
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Lista de usuarios de la sucursal.
        :rtype: list[User]
        """
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
        """
        Obtiene usuarios paginados y aplica filtros opcionales en la consulta.

        :param page: Número de página solicitado.
        :type page: int
        :param limit: Cantidad máxima de resultados.
        :type limit: int
        :param branch_id: Identificador opcional de la sucursal.
        :type branch_id: int or None
        :param search: Texto opcional utilizado para filtrar usuarios.
        :type search: str or None
        :param status: Estado utilizado para la operación o el filtrado.
        :type status: str or None
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Diccionario con los usuarios de la página y el total de resultados.
        :rtype: dict
        """
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
        """
        Obtiene un usuario mediante su identificador interno de PostgreSQL.

        :param user_id: Identificador del usuario.
        :type user_id: int
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Usuario encontrado o ``None``.
        :rtype: User or None
        """
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
        """
        Calcula el siguiente UID local disponible para un dispositivo.

        :param device_id: Identificador opcional del dispositivo.
        :type device_id: int
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Siguiente UID local disponible.
        :rtype: int
        """
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
        """
        Crea una asignación independiente de un usuario en otro dispositivo sin modificar la asignación original.

        :param source_user_id: Identificador interno del usuario de origen.
        :type source_user_id: int
        :param target_device_id: Identificador del dispositivo de destino.
        :type target_device_id: int
        :param uid: UID del usuario en el dispositivo.
        :type uid: int
        :param user_id: Identificador del usuario.
        :type user_id: str
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Nueva asignación del usuario.
        :rtype: User
        :raises ValueError: Si el usuario de origen, el dispositivo de destino o la asignación no son válidos.
        :raises Exception: Si ocurre un error durante la creación de la asignación.
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
        """
        Actualiza el estado de un usuario mediante su identificador interno.

        :param user_id: Identificador del usuario.
        :type user_id: int
        :param status: Estado utilizado para la operación o el filtrado.
        :type status: str
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Usuario actualizado o ``None`` si no existe.
        :rtype: User or None
        :raises Exception: Si ocurre un error al actualizar el estado.
        """
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
        """
        Actualiza el perfil de un usuario mediante su identificador interno.

        :param user_id: Identificador del usuario.
        :type user_id: int
        :param role: Rol del usuario.
        :type role: str
        :param sucursal: Nombre opcional de la sucursal.
        :type sucursal: str
        :param email: Valor utilizado por la operación para ``email``.
        :type email: str
        :param area: Valor utilizado por la operación para ``area``.
        :type area: str
        :param empresa: Empresa asociada.
        :type empresa: str
        :param branch_id: Identificador opcional de la sucursal.
        :type branch_id: int or None
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Usuario actualizado o ``None`` si no existe.
        :rtype: User or None
        :raises Exception: Si ocurre un error al actualizar el perfil.
        """
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
        """
        Actualiza el estado de un usuario mediante su UID.

        :param uid: UID del usuario en el dispositivo.
        :type uid: int
        :param status: Estado utilizado para la operación o el filtrado.
        :type status: str
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Usuario actualizado o ``None`` si no existe.
        :rtype: User or None
        :raises Exception: Si ocurre un error al actualizar el estado.
        """
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
        """
        Actualiza el perfil de un usuario mediante su UID.

        :param uid: UID del usuario en el dispositivo.
        :type uid: int
        :param role: Rol del usuario.
        :type role: str
        :param sucursal: Nombre opcional de la sucursal.
        :type sucursal: str
        :param email: Valor utilizado por la operación para ``email``.
        :type email: str
        :param area: Valor utilizado por la operación para ``area``.
        :type area: str
        :param empresa: Empresa asociada.
        :type empresa: str
        :param branch_id: Identificador opcional de la sucursal.
        :type branch_id: int or None
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Usuario actualizado o ``None`` si no existe.
        :rtype: User or None
        :raises Exception: Si ocurre un error al actualizar el perfil.
        """
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
        """
        Marca como inactivos los usuarios que ya no se encuentran presentes en un dispositivo.

        :param device_id: Identificador opcional del dispositivo.
        :type device_id: int
        :param present_uids: UID presentes actualmente en el dispositivo.
        :type present_uids: list[int]
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Cantidad de usuarios marcados como inactivos.
        :rtype: int
        :raises Exception: Si ocurre un error al actualizar los usuarios ausentes.
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
        """
        Conserva un usuario en la base de datos y lo marca como inactivo.

        :param uid: UID del usuario en el dispositivo.
        :type uid: int
        :param device_id: Identificador opcional del dispositivo.
        :type device_id: int or None
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: ``True`` si el usuario fue marcado como inactivo; de lo contrario, ``False``.
        :rtype: bool
        :raises Exception: Si ocurre un error al conservar al usuario como inactivo.
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
        """
        Registra un nuevo dispositivo biométrico en la base de datos.

        :param nombre: Nombre del dispositivo.
        :type nombre: str
        :param ip: Dirección IP del dispositivo.
        :type ip: str
        :param puerto: Puerto de comunicación del dispositivo.
        :type puerto: int
        :param password: Contraseña del dispositivo.
        :type password: str
        :param sucursal: Nombre opcional de la sucursal.
        :type sucursal: str
        :param ubicacion: Descripción opcional de la ubicación.
        :type ubicacion: str
        :param empresa: Empresa asociada.
        :type empresa: str
        :param branch_id: Identificador opcional de la sucursal.
        :type branch_id: int or None
        :param auto_sync_enabled: Indica si la sincronización automática está habilitada.
        :type auto_sync_enabled: bool
        :param sync_interval_minutes: Intervalo de sincronización automática expresado en minutos.
        :type sync_interval_minutes: int
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Dispositivo registrado.
        :rtype: Device
        :raises DataValidationError: Si ya existe un dispositivo con la misma dirección IP.
        :raises Exception: Si ocurre un error durante el registro.
        """
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
        """
        Obtiene todos los dispositivos registrados.

        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Lista de dispositivos registrados.
        :rtype: list[Device]
        """
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
        """
        Obtiene los dispositivos asociados a una sucursal.

        :param branch_id: Identificador opcional de la sucursal.
        :type branch_id: int
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Lista de dispositivos de la sucursal.
        :rtype: list[Device]
        """
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
        """
        Obtiene un dispositivo mediante su identificador.

        :param device_id: Identificador opcional del dispositivo.
        :type device_id: int
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Dispositivo encontrado o ``None``.
        :rtype: Device or None
        """
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
        """
        Actualiza los datos configurables de un dispositivo registrado.

        :param device_id: Identificador opcional del dispositivo.
        :type device_id: int
        :param nombre: Nombre del dispositivo.
        :type nombre: str
        :param ip: Dirección IP del dispositivo.
        :type ip: str
        :param puerto: Puerto de comunicación del dispositivo.
        :type puerto: int
        :param password: Contraseña del dispositivo.
        :type password: str
        :param sucursal: Nombre opcional de la sucursal.
        :type sucursal: str
        :param ubicacion: Descripción opcional de la ubicación.
        :type ubicacion: str
        :param empresa: Empresa asociada.
        :type empresa: str
        :param activo: Indica si el dispositivo debe permanecer activo.
        :type activo: bool
        :param branch_id: Identificador opcional de la sucursal.
        :type branch_id: int or None
        :param auto_sync_enabled: Indica si la sincronización automática está habilitada.
        :type auto_sync_enabled: bool or None
        :param sync_interval_minutes: Intervalo de sincronización automática expresado en minutos.
        :type sync_interval_minutes: int or None
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Dispositivo actualizado o ``None`` si no existe.
        :rtype: Device or None
        :raises DataValidationError: Si la contraseña o el intervalo de sincronización no son válidos.
        :raises Exception: Si ocurre un error durante la actualización.
        """
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
        """
        Actualiza el estado y, opcionalmente, la última conexión de un dispositivo.

        :param device_id: Identificador opcional del dispositivo.
        :type device_id: int
        :param estado: Estado que se debe asignar al dispositivo.
        :type estado: str
        :param ultima_sincronizacion: Fecha y hora opcionales de la última conexión.
        :type ultima_sincronizacion: datetime
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Dispositivo actualizado o ``None`` si no existe.
        :rtype: Device or None
        :raises Exception: Si ocurre un error al actualizar el estado.
        """
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
        """
        Actualiza el estado y la fecha de la última sincronización real de un dispositivo.

        :param device_id: Identificador opcional del dispositivo.
        :type device_id: int
        :param estado: Estado que se debe asignar al dispositivo.
        :type estado: str
        :param synced_at: Fecha y hora opcionales de la sincronización.
        :type synced_at: datetime
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Dispositivo actualizado o ``None`` si no existe.
        :rtype: Device or None
        :raises Exception: Si ocurre un error al actualizar la sincronización.
        """
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
        """
        Inactiva un dispositivo registrado sin eliminarlo de la base de datos.

        :param device_id: Identificador opcional del dispositivo.
        :type device_id: int
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: ``True`` si el dispositivo fue inactivado; de lo contrario, ``False``.
        :rtype: bool
        :raises Exception: Si ocurre un error al inactivar el dispositivo.
        """
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
        """
        Reactiva un dispositivo previamente inactivado.

        :param device_id: Identificador opcional del dispositivo.
        :type device_id: int
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: ``True`` si el dispositivo fue activado; de lo contrario, ``False``.
        :rtype: bool
        :raises Exception: Si ocurre un error al activar el dispositivo.
        """
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
    ) -> AttendanceModel:
        """
        Guarda un registro individual de asistencia en la base de datos.

        :param uid: UID del usuario en el dispositivo.
        :type uid: int
        :param user_id: Identificador del usuario.
        :type user_id: str
        :param name: Nombre del usuario o de la sucursal, según la operación.
        :type name: str
        :param timestamp: Fecha y hora del registro de asistencia.
        :type timestamp: datetime
        :param status: Estado utilizado para la operación o el filtrado.
        :type status: str
        :param branch_id: Identificador opcional de la sucursal.
        :type branch_id: int or None
        :param device_id: Identificador opcional del dispositivo.
        :type device_id: int or None
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Registro de asistencia guardado.
        :rtype: :class:`app.models.attendance.AttendanceRecord`
        :raises Exception: Si ocurre un error al guardar la asistencia.
        """
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

            record = AttendanceModel(
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
        """
        Guarda múltiples registros de asistencia y descarta registros inválidos o duplicados.

        :param records: Registros de asistencia que se deben procesar.
        :type records: list[dict]
        :param branch_id: Identificador opcional de la sucursal.
        :type branch_id: int or None
        :param device_id: Identificador opcional del dispositivo.
        :type device_id: int or None
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Cantidad de registros nuevos insertados.
        :rtype: int
        :raises Exception: Si ocurre un error durante el procesamiento o guardado de los registros.
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
                    AttendanceModel.device_id == record_device_id,
                    AttendanceModel.timestamp == timestamp,
                    AttendanceModel.status == status,
                ]
                if uid is not None:
                    identity_filters.append(AttendanceModel.uid == uid)
                else:
                    identity_filters.append(AttendanceModel.user_id == user_id)

                existing = (
                    db.query(AttendanceModel)
                    .filter(and_(*identity_filters))
                    .first()
                )

                if existing:
                    duplicates += 1
                    continue

                db.add(
                    AttendanceModel(
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
        """
        Obtiene registros de asistencia paginados y filtrados directamente en la base de datos.

        :param page: Número de página solicitado.
        :type page: int
        :param limit: Cantidad máxima de resultados.
        :type limit: int
        :param start_date: Fecha inicial del rango.
        :type start_date: datetime or None
        :param end_date: Fecha final del rango.
        :type end_date: datetime or None
        :param branch_id: Identificador opcional de la sucursal.
        :type branch_id: int or None
        :param user_ids: Identificadores o claves de asignación utilizados para filtrar.
        :type user_ids: list[str] or None
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Diccionario con los registros de la página y el total de resultados.
        :rtype: dict
        """
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            query = db.query(AttendanceModel)

            if start_date is not None:
                query = query.filter(AttendanceModel.timestamp >= start_date)
            if end_date is not None:
                query = query.filter(AttendanceModel.timestamp <= end_date)
            if branch_id is not None:
                query = query.filter(AttendanceModel.branch_id == branch_id)
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
                                AttendanceModel.device_id == selected_device_id,
                                AttendanceModel.user_id == selected_user_id,
                            )
                        )
                    else:
                        legacy_user_ids.append(raw)

                filters = list(assignment_filters)
                if legacy_user_ids:
                    filters.append(
                        AttendanceModel.user_id.in_(legacy_user_ids)
                    )

                if filters:
                    query = query.filter(or_(*filters))

            total = query.count()
            items = (
                query.order_by(AttendanceModel.timestamp.desc())
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
    ) -> List[AttendanceModel]:
        """
        Obtiene registros de asistencia incluidos en un rango de fechas.

        :param start_date: Fecha inicial del rango.
        :type start_date: datetime
        :param end_date: Fecha final del rango.
        :type end_date: datetime
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Lista de registros incluidos en el rango.
        :rtype: list[AttendanceModel]
        """
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            return (
                db.query(AttendanceModel)
                .filter(
                    and_(
                        AttendanceModel.timestamp >= start_date,
                        AttendanceModel.timestamp <= end_date,
                    )
                )
                .order_by(AttendanceModel.timestamp.desc())
                .all()
            )
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_attendance_by_branch(
        branch_id: int,
        db: Optional[Session] = None,
    ) -> List[AttendanceModel]:
        """
        Obtiene los registros de asistencia asociados a una sucursal.

        :param branch_id: Identificador opcional de la sucursal.
        :type branch_id: int
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Lista de registros de asistencia de la sucursal.
        :rtype: list[AttendanceModel]
        """
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            return (
                db.query(AttendanceModel)
                .filter(AttendanceModel.branch_id == branch_id)
                .order_by(AttendanceModel.timestamp.desc())
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
    ) -> List[AttendanceModel]:
        """
        Obtiene los registros de asistencia de un usuario específico.

        :param user_id: Identificador del usuario.
        :type user_id: str
        :param start_date: Fecha inicial del rango.
        :type start_date: datetime or None
        :param end_date: Fecha final del rango.
        :type end_date: datetime or None
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Lista de registros de asistencia del usuario.
        :rtype: list[AttendanceModel]
        """
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            query = db.query(AttendanceModel).filter(AttendanceModel.user_id == user_id)

            if start_date and end_date:
                query = query.filter(
                    and_(
                        AttendanceModel.timestamp >= start_date,
                        AttendanceModel.timestamp <= end_date,
                    )
                )

            return query.order_by(AttendanceModel.timestamp.desc()).all()

        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_attendance_dates_summary(db: Optional[Session] = None) -> List[Dict]:
        """
        Obtiene las fechas que contienen asistencias y el total de registros por día.

        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Lista de fechas con el total de registros correspondiente.
        :rtype: list[dict]
        """
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            attendance_date = func.date(AttendanceModel.timestamp)

            rows = (
                db.query(
                    attendance_date.label("fecha"),
                    func.count(AttendanceModel.id).label("total"),
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
        """
        Obtiene incidencias de prenómina incluidas en un rango de fechas.

        :param start_date: Fecha inicial del rango.
        :type start_date: date
        :param end_date: Fecha final del rango.
        :type end_date: date
        :param branch_id: Identificador opcional de la sucursal.
        :type branch_id: int or None
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Lista de incidencias encontradas.
        :rtype: list[PayrollIncident]
        """
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            query = (
                db.query(PayrollIncident)
                .filter(
                    PayrollIncident.is_active.is_(True),
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
                PayrollIncident.source_hora.asc().nullsfirst(),
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
        hora=None,
        incidencia: str = "",
        descripcion: str = None,
        color: str = "#BAE6FD",
        incident_id: Optional[int] = None,
        device_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> PayrollIncident:
        """
        Crea o actualiza una incidencia de prenómina para una asignación concreta.

        :param user_id: Identificador del usuario.
        :type user_id: str
        :param fecha: Fecha de la incidencia.
        :type fecha: date
        :param hora: Hora opcional asociada a la incidencia.
        :type hora: time or None
        :param incidencia: Nombre o tipo de la incidencia.
        :type incidencia: str
        :param descripcion: Descripción opcional de la incidencia.
        :type descripcion: str
        :param color: Color hexadecimal asociado a la incidencia.
        :type color: str
        :param incident_id: Identificador opcional de la incidencia que se debe actualizar.
        :type incident_id: int or None
        :param device_id: Identificador opcional del dispositivo.
        :type device_id: int or None
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Incidencia creada o actualizada.
        :rtype: PayrollIncident
        :raises DataValidationError: Si los datos de la incidencia, el usuario o el dispositivo no son válidos.
        :raises Exception: Si ocurre un error durante el guardado.
        """
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            clean_user_id = str(user_id).strip()
            clean_incidencia = str(incidencia or "").strip()
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
                incident.incidencia = clean_incidencia
                incident.color = clean_color
                incident.is_active = True
                incident.deleted_at = None

                # Sólo cambia la incidencia elegida por su id. Las demás
                # incidencias del mismo día permanecen intactas.
                incident.source_fecha = fecha
                incident.source_hora = hora
                incident.moved_attendance = None
                incident.updated_at = datetime.utcnow()

                db.commit()
                db.refresh(incident)
                return incident

            # Sin id siempre se inserta una incidencia nueva. Ya no se busca ni
            # se reemplaza otra por device_id + user_id + fecha.
            incident = PayrollIncident(
                uid=user.uid,
                device_id=device_id,
                user_id=clean_user_id,
                fecha=fecha,
                incidencia=clean_incidencia,
                color=clean_color,
                source_fecha=fecha,
                source_hora=hora,
                moved_attendance=None,
                is_active=True,
                deleted_at=None,
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
        """
        Conserva una incidencia de prenómina y la marca como inactiva.

        :param incident_id: Identificador opcional de la incidencia que se debe actualizar.
        :type incident_id: int
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: ``True`` si la incidencia fue marcada como inactiva; de lo contrario, ``False``.
        :rtype: bool
        :raises Exception: Si ocurre un error al conservar la incidencia como inactiva.
        """
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            incident = (
                db.query(PayrollIncident)
                .filter(
                    PayrollIncident.id == incident_id,
                    PayrollIncident.is_active.is_(True),
                )
                .first()
            )

            if not incident:
                return False

            incident.is_active = False
            incident.deleted_at = datetime.utcnow()
            incident.updated_at = datetime.utcnow()
            db.commit()

            return True

        except Exception as e:
            db.rollback()
            logger.error(
                "Error al conservar incidencia de prenómina %s como inactiva: %s",
                incident_id,
                str(e),
            )
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
        """
        Crea una nueva sucursal en la base de datos.

        :param name: Nombre del usuario o de la sucursal, según la operación.
        :type name: str
        :param address: Dirección opcional de la sucursal.
        :type address: str
        :param is_active: Indica si la sucursal debe permanecer activa.
        :type is_active: bool
        :param status: Estado utilizado para la operación o el filtrado.
        :type status: str
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Sucursal creada.
        :rtype: Branch
        :raises DataValidationError: Si ya existe una sucursal con el mismo nombre.
        :raises Exception: Si ocurre un error durante la creación.
        """
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
        """
        Obtiene todas las sucursales registradas.

        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Lista de sucursales registradas.
        :rtype: list[Branch]
        """
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
        """
        Obtiene una sucursal mediante su identificador.

        :param branch_id: Identificador opcional de la sucursal.
        :type branch_id: int
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Sucursal encontrada o ``None``.
        :rtype: Branch or None
        """
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
        """
        Actualiza los datos y el estado de una sucursal.

        :param branch_id: Identificador opcional de la sucursal.
        :type branch_id: int
        :param name: Nombre del usuario o de la sucursal, según la operación.
        :type name: str
        :param address: Dirección opcional de la sucursal.
        :type address: str
        :param is_active: Indica si la sucursal debe permanecer activa.
        :type is_active: bool
        :param status: Estado utilizado para la operación o el filtrado.
        :type status: str
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Sucursal actualizada o ``None`` si no existe.
        :rtype: Branch or None
        :raises Exception: Si ocurre un error durante la actualización.
        """
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
        """
        Crea un registro de auditoría.

        :param accion: Nombre de la acción auditada.
        :type accion: str
        :param detalle: Descripción de la acción auditada.
        :type detalle: str
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Registro de auditoría creado.
        :rtype: Log
        :raises Exception: Si ocurre un error al crear el registro de auditoría.
        """
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
        """
        Obtiene los registros de auditoría más recientes.

        :param limit: Cantidad máxima de resultados.
        :type limit: int
        :param db: Sesión opcional de SQLAlchemy. Si no se proporciona, se crea una sesión interna.
        :type db: Session or None
        :return: Lista de registros de auditoría.
        :rtype: list[Log]
        """
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