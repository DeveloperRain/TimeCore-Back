from typing import Optional, Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.db_service import DBService
from app.utils.response import success

router = APIRouter(
    prefix="/branches",
    tags=["Sucursales"],
)

BranchStatus = Literal["Activo", "Inactivo", "Baja"]


class BranchCreate(BaseModel):
    name: str
    address: Optional[str] = None
    status: Optional[BranchStatus] = "Activo"


class BranchUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    is_active: Optional[bool] = None
    status: Optional[BranchStatus] = None


def normalize_branch_status(
    status: Optional[str],
    is_active: Optional[bool] = None,
) -> str:
    if status:
        status_clean = status.strip().lower()

        if status_clean == "activo":
            return "Activo"

        if status_clean == "inactivo":
            return "Inactivo"

        if status_clean == "baja":
            return "Baja"

    if is_active is True:
        return "Activo"

    if is_active is False:
        return "Inactivo"

    return "Activo"


def branch_to_dict(branch):
    status = normalize_branch_status(
        getattr(branch, "status", None),
        getattr(branch, "is_active", None),
    )

    return {
        "id": branch.id,
        "name": branch.name,
        "address": branch.address,
        "is_active": status == "Activo",
        "status": status,
        "created_at": branch.created_at.isoformat() if branch.created_at else None,
        "updated_at": branch.updated_at.isoformat() if branch.updated_at else None,
    }


def user_to_dict(user):
    return {
        "id": getattr(user, "id", None),
        "uid": getattr(user, "uid", None),
        "user_id": getattr(user, "user_id", None),
        "name": getattr(user, "name", None),
        "role": getattr(user, "role", None),
        "email": getattr(user, "email", None),
        "area": getattr(user, "area", None),
        "empresa": getattr(user, "empresa", None),
        "sucursal": getattr(user, "sucursal", None),
        "branch_id": getattr(user, "branch_id", None),
        "status": getattr(user, "status", None),
        "device_id": getattr(user, "device_id", None),
        "device_code": getattr(user, "device_code", None),
    }


def device_to_dict(device):
    return {
        "id": getattr(device, "id", None),
        "nombre": getattr(device, "nombre", None),
        "name": getattr(device, "name", None),
        "ip": getattr(device, "ip", None),
        "ip_address": getattr(device, "ip_address", None),
        "puerto": getattr(device, "puerto", None),
        "port": getattr(device, "port", None),
        "sucursal": getattr(device, "sucursal", None),
        "ubicacion": getattr(device, "ubicacion", None),
        "location": getattr(device, "location", None),
        "activo": getattr(device, "activo", None),
        "is_active": getattr(device, "is_active", None),
        "status": getattr(device, "status", None),
        "branch_id": getattr(device, "branch_id", None),
    }


def attendance_to_dict(record):
    if hasattr(record, "to_dict"):
        return record.to_dict()

    return {
        "id": getattr(record, "id", None),
        "uid": getattr(record, "uid", None),
        "user_id": getattr(record, "user_id", None),
        "name": getattr(record, "name", None),
        "timestamp": getattr(record, "timestamp", None).isoformat()
        if getattr(record, "timestamp", None)
        else None,
        "punch_time": getattr(record, "punch_time", None).isoformat()
        if getattr(record, "punch_time", None)
        else None,
        "branch_id": getattr(record, "branch_id", None),
        "device_id": getattr(record, "device_id", None),
        "device_code": getattr(record, "device_code", None),
    }


@router.get("/", summary="Obtener sucursales")
def get_branches():
    branches = DBService.get_all_branches()
    data = [branch_to_dict(b) for b in branches]

    return success(
        data=data,
        message=f"Se obtuvieron {len(data)} sucursales",
    )


@router.get("/{branch_id}", summary="Obtener sucursal por ID")
def get_branch(branch_id: int):
    branch = DBService.get_branch_by_id(branch_id)

    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    return success(
        data=branch_to_dict(branch),
        message="Sucursal obtenida correctamente",
    )


@router.get("/{branch_id}/dashboard", summary="Obtener dashboard de una sucursal")
def get_branch_dashboard(branch_id: int):
    branch = DBService.get_branch_by_id(branch_id)

    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    usuarios = DBService.get_users_by_branch(branch_id)
    devices = DBService.get_devices_by_branch(branch_id)
    attendance = DBService.get_attendance_by_branch(branch_id)

    active_devices = [
        device
        for device in devices
        if getattr(device, "activo", getattr(device, "is_active", True))
    ]

    data = {
        "branch": branch_to_dict(branch),
        "total_empleados": len(usuarios),
        "relojes_conectados": len(active_devices),
        "total_relojes": len(devices),
        "asistencias_registradas": len(attendance),
        "sucursales_activas": 1 if normalize_branch_status(branch.status, branch.is_active) == "Activo" else 0,
        "devices": [device_to_dict(device) for device in devices],
    }

    return success(
        data=data,
        message=f"Dashboard de {branch.name} obtenido correctamente",
    )


@router.get("/{branch_id}/users", summary="Obtener empleados de una sucursal")
def get_branch_users(branch_id: int):
    branch = DBService.get_branch_by_id(branch_id)

    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    usuarios = DBService.get_users_by_branch(branch_id)

    return success(
        data=[user_to_dict(user) for user in usuarios],
        message=f"Se obtuvieron {len(usuarios)} empleados de {branch.name}",
    )


@router.get("/{branch_id}/devices", summary="Obtener relojes de una sucursal")
def get_branch_devices(branch_id: int):
    branch = DBService.get_branch_by_id(branch_id)

    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    devices = DBService.get_devices_by_branch(branch_id)

    return success(
        data=[device_to_dict(device) for device in devices],
        message=f"Se obtuvieron {len(devices)} relojes de {branch.name}",
    )


@router.get("/{branch_id}/attendance", summary="Obtener asistencias de una sucursal")
def get_branch_attendance(branch_id: int):
    branch = DBService.get_branch_by_id(branch_id)

    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    attendance = DBService.get_attendance_by_branch(branch_id)

    return success(
        data=[attendance_to_dict(record) for record in attendance],
        message=f"Se obtuvieron {len(attendance)} asistencias de {branch.name}",
    )


@router.post("/", summary="Crear sucursal")
def create_branch(payload: BranchCreate):
    status = normalize_branch_status(payload.status)

    branch = DBService.create_branch(
        name=payload.name,
        address=payload.address,
        status=status,
        is_active=status == "Activo",
    )

    DBService.create_log(
        accion="Sucursal creada",
        detalle=f"Se creó la sucursal {branch.name}",
    )

    return success(
        data=branch_to_dict(branch),
        message="Sucursal creada correctamente",
    )


@router.put("/{branch_id}", summary="Actualizar sucursal")
def update_branch(branch_id: int, payload: BranchUpdate):
    status = payload.status

    if status is None and payload.is_active is not None:
        status = "Activo" if payload.is_active else "Inactivo"

    if status is not None:
        status = normalize_branch_status(status)

    branch = DBService.update_branch(
        branch_id=branch_id,
        name=payload.name,
        address=payload.address,
        is_active=status == "Activo" if status is not None else payload.is_active,
        status=status,
    )

    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    DBService.create_log(
        accion="Sucursal actualizada",
        detalle=f"Se actualizó la sucursal {branch.name}",
    )

    return success(
        data=branch_to_dict(branch),
        message="Sucursal actualizada correctamente",
    )
