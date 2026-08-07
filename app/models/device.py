from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.database.connection import Base


class Device(Base):
    """Modelo ORM representativo de la tabla de dispositivos (devices)."""
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)

    name = Column(String(100), nullable=False)
    ip = Column(String(45), nullable=False, unique=True)
    port = Column(Integer, default=4370)

    branch_id = Column(
        Integer,
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    location = Column(String(100))
    description = Column(Text)
    empresa = Column(String(100), nullable=True)
    password = Column(String(100), nullable=False, default="")

    is_active = Column(Boolean, default=True)

    last_connection = Column(DateTime)
    last_sync_at = Column(DateTime)

    auto_sync_enabled = Column(Boolean, nullable=False, default=True)
    sync_interval_minutes = Column(Integer, nullable=False, default=4)

    status = Column(String(20), default="Desconectado")

    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    branch = relationship("Branch", back_populates="devices")
    users = relationship("User", back_populates="device", passive_deletes=True)
    attendance_records = relationship(
        "AttendanceRecord",
        back_populates="device",
        passive_deletes=True,
    )

    def to_dict(self):
        """Convierte la instancia del modelo en un diccionario.

        :return: Un diccionario con los datos serializados del dispositivo, incluyendo alias para varios campos.
        :rtype: dict
        """
        return {
            "id": self.id,
            "name": self.name,
            "nombre": self.name,
            "ip": self.ip,
            "ip_address": self.ip,
            "port": self.port,
            "puerto": self.port,
            "branch_id": self.branch_id,
            "location": self.location,
            "sucursal": self.location,
            "description": self.description,
            "ubicacion": self.description,
            "empresa": self.empresa,
            "password": self.password,
            "device_password": self.password,
            "is_active": self.is_active,
            "activo": self.is_active,
            "status": self.status,
            "estado": self.status,
            "last_connection": self.last_connection.isoformat()
            if self.last_connection
            else None,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "auto_sync_enabled": bool(self.auto_sync_enabled),
            "sync_interval_minutes": int(self.sync_interval_minutes or 4),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }