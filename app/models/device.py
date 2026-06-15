"""Modelo de relojes biométricos ZKTeco."""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime
from app.database.connection import Base


class Device(Base):
    """Representa un reloj biométrico registrado."""

    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)

    nombre = Column(String(100), nullable=False)
    ip = Column(String(50), nullable=False, unique=True)
    puerto = Column(Integer, nullable=False, default=4370)

    sucursal = Column(String(150), nullable=True)
    ubicacion = Column(String(200), nullable=True)

    activo = Column(Boolean, default=True)
    estado = Column(String(30), default="Desconocido")

    ultima_sincronizacion = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)