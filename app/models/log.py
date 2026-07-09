from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.database.connection import Base


class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    accion = Column(String(100), nullable=False)
    detalle = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    