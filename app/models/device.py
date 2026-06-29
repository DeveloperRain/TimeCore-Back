from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.database.connection import Base


class Device(Base):
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

    is_active = Column(Boolean, default=True)

    last_connection = Column(DateTime)

    status = Column(String(20), default="Desconectado")

    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    branch = relationship("Branch", back_populates="devices")

    def to_dict(self):
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
            "is_active": self.is_active,
            "activo": self.is_active,
            "status": self.status,
            "estado": self.status,
            "last_connection": self.last_connection.isoformat()
            if self.last_connection
            else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }