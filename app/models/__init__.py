"""Modelos ORM de la aplicación."""
from app.models.user import User, UserRole
from app.models.attendance import AttendanceRecord
from app.models.device import Device
from app.models.log import Log

__all__ = ["User", "UserRole", "AttendanceRecord", "Device", "Log"]

