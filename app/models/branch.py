from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime
from app.database.connection import Base


class Branch(Base):
    __tablename__ = "branches"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    address = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), nullable=True, default="Activo")

