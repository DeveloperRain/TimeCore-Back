"""Modelo ORM para incidencias manuales de prenomina."""
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import relationship

from app.database.connection import Base


class PayrollIncident(Base):
    """Incidencia manual capturada para la vista de prenomina."""

    __tablename__ = "payroll_incidents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    uid = Column(Integer, ForeignKey("users.uid", ondelete="CASCADE"), nullable=True, index=True)
    device_id = Column(
        Integer,
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = Column(String(50), nullable=False, index=True)
    fecha = Column(Date, nullable=False, index=True)
    hora = Column(Time, nullable=False)
    incidencia = Column(String(120), nullable=False)
    descripcion = Column(String(255), nullable=True)
    color = Column(String(7), nullable=False, default="#BAE6FD")
    source_fecha = Column(Date, nullable=True, index=True)
    source_hora = Column(Time, nullable=True)
    moved_attendance = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User")

    def to_dict(self):
        """Convierte a diccionario."""
        return {
            "id": self.id,
            "uid": self.uid,
            "device_id": self.device_id,
            "assignment_key": f"{self.device_id or 0}:{self.user_id}",
            "user_id": self.user_id,
            "fecha": self.fecha.isoformat() if self.fecha else None,
            "hora": self.hora.strftime("%H:%M") if self.hora else None,
            "incidencia": self.incidencia,
            "descripcion": self.descripcion,
            "color": self.color or "#BAE6FD",
            "source_fecha": self.source_fecha.isoformat() if self.source_fecha else None,
            "source_hora": self.source_hora.strftime("%H:%M") if self.source_hora else None,
            "moved_attendance": self.moved_attendance,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
