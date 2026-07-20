"""Modelo ORM para tabla de registros de asistencia."""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.database.connection import Base


class AttendanceRecord(Base):
    """Tabla de registros de asistencia sincronizados del reloj."""
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    uid = Column(Integer, nullable=True, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False)

    device_id = Column(
        Integer,
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    branch_id = Column(
        Integer,
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    timestamp = Column(DateTime, nullable=False, index=True)
    status = Column(String(20), nullable=False)
    synced_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    branch = relationship("Branch", back_populates="attendance_records")
    device = relationship("Device", back_populates="attendance_records")

    def to_dict(self):
        """Convierte a diccionario."""
        return {
            "id": self.id,
            "uid": self.uid,
            "user_id": self.user_id,
            "name": self.name,
            "branch_id": self.branch_id,
            "device_id": self.device_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "status": self.status,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
        }