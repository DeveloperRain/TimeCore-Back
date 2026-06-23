from typing import Optional, Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.db_service import DBService
from app.utils.response import success

router = APIRouter(
    prefix="/branches",
    tags=["Sucursales"]
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


def normalize_branch_status(status: Optional[str], is_active: Optional[bool] = None) -> str:
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
    status = normalize_branch_status(branch.status, branch.is_active)

    return {
        "id": branch.id,
        "name": branch.name,
        "address": branch.address,
        "is_active": status == "Activo",
        "status": status,
        "created_at": branch.created_at.isoformat() if branch.created_at else None,
        "updated_at": branch.updated_at.isoformat() if branch.updated_at else None,
    }


@router.get("/", summary="Obtener sucursales")
def get_branches():
    branches = DBService.get_all_branches()
    data = [branch_to_dict(b) for b in branches]

    return success(
        data=data,
        message=f"Se obtuvieron {len(data)} sucursales"
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
        detalle=f"Se creó la sucursal {branch.name}"
    )

    return success(
        data=branch_to_dict(branch),
        message="Sucursal creada correctamente"
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
        detalle=f"Se actualizó la sucursal {branch.name}"
    )

    return success(
        data=branch_to_dict(branch),
        message="Sucursal actualizada correctamente"
    )