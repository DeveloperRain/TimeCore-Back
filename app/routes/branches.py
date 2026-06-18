from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.db_service import DBService
from app.utils.response import success

router = APIRouter(
    prefix="/branches",
    tags=["Sucursales"]
)


class BranchCreate(BaseModel):
    name: str
    address: Optional[str] = None


class BranchUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/", summary="Obtener sucursales")
def get_branches():
    branches = DBService.get_all_branches()

    data = [
        {
            "id": b.id,
            "name": b.name,
            "address": b.address,
            "is_active": b.is_active,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "updated_at": b.updated_at.isoformat() if b.updated_at else None,
        }
        for b in branches
    ]

    return success(
        data=data,
        message=f"Se obtuvieron {len(data)} sucursales"
    )


@router.post("/", summary="Crear sucursal")
def create_branch(payload: BranchCreate):
    branch = DBService.create_branch(
        name=payload.name,
        address=payload.address
    )

    DBService.create_log(
        accion="Sucursal creada",
        detalle=f"Se creó la sucursal {branch.name}"
    )

    return success(
        data={
            "id": branch.id,
            "name": branch.name,
            "address": branch.address,
            "is_active": branch.is_active,
        },
        message="Sucursal creada correctamente"
    )


@router.put("/{branch_id}", summary="Actualizar sucursal")
def update_branch(branch_id: int, payload: BranchUpdate):
    branch = DBService.update_branch(
        branch_id=branch_id,
        name=payload.name,
        address=payload.address,
        is_active=payload.is_active,
    )

    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    DBService.create_log(
        accion="Sucursal actualizada",
        detalle=f"Se actualizó la sucursal {branch.name}"
    )

    return success(
        data={
            "id": branch.id,
            "name": branch.name,
            "address": branch.address,
            "is_active": branch.is_active,
        },
        message="Sucursal actualizada correctamente"
    )