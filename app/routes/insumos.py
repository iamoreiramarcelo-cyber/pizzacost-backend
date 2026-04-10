"""Insumo (supply/ingredient) routes for PizzaCost Pro."""

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.database import get_supabase_client
from app.middleware.auth import get_current_user, UserContext
from app.middleware.audit import audit_log
from app.models import (
    InsumoCreate,
    InsumoResponse,
    InsumoUpdate,
    PaginatedResponse,
    PaginationMeta,
    SuccessMessage,
)
from app.services import insumo_service, activity_service

router = APIRouter(prefix="/api/v1/insumos", tags=["Insumos"])


@router.get("", response_model=PaginatedResponse[InsumoResponse])
async def list_insumos(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """List all insumos for the authenticated user with pagination."""
    items, total = await insumo_service.list_insumos(
        db, user_id=user.id, page=page, per_page=per_page
    )
    return PaginatedResponse(
        data=[InsumoResponse(**item) for item in items],
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
    )


@router.get("/{insumo_id}", response_model=InsumoResponse)
async def get_insumo(
    insumo_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Get a single insumo by ID."""
    item = await insumo_service.get_insumo(db, user_id=user.id, insumo_id=insumo_id)
    return InsumoResponse(**item)


@router.post("", response_model=InsumoResponse, status_code=201)
async def create_insumo(
    body: InsumoCreate,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Create a new insumo."""
    data = body.model_dump()
    data["unidade"] = data["unidade"].value if hasattr(data["unidade"], "value") else data["unidade"]

    item = await insumo_service.create_insumo(db, user_id=user.id, data=data)

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="create",
        resource="insumos",
        resource_id=str(item["id"]),
        new_data=item,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="create_insumo",
        metadata={"insumo_id": str(item["id"]), "nome": item["nome"]},
    )

    return InsumoResponse(**item)


@router.put("/{insumo_id}", response_model=InsumoResponse)
async def update_insumo(
    insumo_id: str,
    body: InsumoUpdate,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Update an existing insumo."""
    data = body.model_dump(exclude_none=True)
    if "unidade" in data and hasattr(data["unidade"], "value"):
        data["unidade"] = data["unidade"].value

    old_item = await insumo_service.get_insumo(db, user_id=user.id, insumo_id=insumo_id)
    item = await insumo_service.update_insumo(
        db, user_id=user.id, insumo_id=insumo_id, data=data
    )

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="update",
        resource="insumos",
        resource_id=insumo_id,
        old_data=old_item,
        new_data=item,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="update_insumo",
        metadata={"insumo_id": insumo_id},
    )

    return InsumoResponse(**item)


@router.delete("/{insumo_id}", response_model=SuccessMessage)
async def delete_insumo(
    insumo_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Delete an insumo."""
    old_item = await insumo_service.get_insumo(db, user_id=user.id, insumo_id=insumo_id)
    await insumo_service.delete_insumo(db, user_id=user.id, insumo_id=insumo_id)

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="delete",
        resource="insumos",
        resource_id=insumo_id,
        old_data=old_item,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="delete_insumo",
        metadata={"insumo_id": insumo_id},
    )

    return SuccessMessage(message="Insumo deleted successfully.")
