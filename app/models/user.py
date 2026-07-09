from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import relationship
from app.database.connection import Base
import enum


class UserRole(str, enum.Enum):
    """Roles disponibles."""
    usuario = "usuario"
    admin = "admin"


class User(Base):
    """Tabla de usuarios sincronizados del reloj biométrico."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    uid = Column(Integer, unique=True, nullable=False, index=True)
    user_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.usuario, nullable=False)

    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    status = Column(String(20), default="Activo")
    sucursal = Column(String(100), nullable=True)
    email = Column(String(150), nullable=True)
    area = Column(String(100), nullable=True)
    empresa = Column(String(100), nullable=True)

    branch = relationship("Branch", back_populates="users")
    attendance_records = relationship(
        "AttendanceRecord",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        """Convierte a diccionario."""
        return {
            "id": self.id,
            "uid": self.uid,
            "user_id": self.user_id,
            "name": self.name,
            "role": self.role.value if hasattr(self.role, "value") else str(self.role),
            "branch_id": self.branch_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "status": self.status,
            "sucursal": self.sucursal,
            "email": self.email,
            "area": self.area,
            "empresa": self.empresa,
        }
