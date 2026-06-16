from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from app.database.connection import Base

class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)

    name = Column(String(100), nullable=False)
    ip = Column(String(45), nullable=False, unique=True)
    port = Column(Integer, default=4370)

    location = Column(String(100))
    description = Column(Text)

    is_active = Column(Boolean, default=True)

    last_connection = Column(DateTime)

    status = Column(String(20), default="Desconectado")

    created_at = Column(DateTime)
    updated_at = Column(DateTime)