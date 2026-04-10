"""Borda (pizza crust/border) routes for PizzaCost Pro."""

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.database import get_supabase_client
from app.middleware.auth import get_current_user, UserContext
from app.middleware.audit import audit_log
from app.models import (
    BordaCreate,
    BordaResponse,
    BordaUpdate,
    PaginatedResponse,
    PaginationMeta,
    SuccessMessage,
)
from app.services import borda_service, activity_service

router = APIRouter(prefix="/api/v1/bordas", tags=["Bordas"])


@router.get("", response_model=PaginatedResponse[BordaResponse])
async def list_bordas(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """List all bordas for the authenticated user."""
    items, total = await borda_service.list_bordas(
        db, user_id=user.id, page=page, per_page=per_page
    )
    return PaginatedResponse(
        data=[BordaResponse(**item) for item in items],
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
    )


@router.get("/{borda_id}", response_model=BordaResponse)
async def get_borda(
    borda_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Get a single borda by ID."""
    item = await borda_service.get_borda(db, user_id=user.id, borda_id=borda_id)
    return BordaResponse(**item)


@router.post("", response_model=BordaResponse, status_code=201)
async def create_borda(
    body: BordaCreate,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Create a new borda. Checks subscription limit."""
    data = body.model_dump()
    data["tamanho_id"] = str(data["tamanho_id"])
    data["ingredientes"] = [
        ing if isinstance(ing, dict) else ing.model_dump()
        for ing in body.ingredientes
    ]

    item = await borda_service.create_borda(db, user_id=user.id, data=data)

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="create",
        resource="bordas",
        resource_id=str(item["id"]),
        new_data=item,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="create_borda",
        metadata={"borda_id": str(item["id"]), "nome": item["nome"]},
    )

    return BordaResponse(**item)


@router.put("/{borda_id}", response_model=BordaResponse)
async def update_borda(
    borda_id: str,
    body: BordaUpdate,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Update an existing borda."""
    data = body.model_dump(exclude_none=True)
    if "tamanho_id" in data:
        data["tamanho_id"] = str(data["tamanho_id"])

    old_item = await borda_service.get_borda(db, user_id=user.id, borda_id=borda_id)
    item = await borda_service.update_borda(
        db, user_id=user.id, borda_id=borda_id, data=data
    )

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="update",
        resource="bordas",
        resource_id=borda_id,
        old_data=old_item,
        new_data=item,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="update_borda",
        metadata={"borda_id": borda_id},
    )

    return BordaResponse(**item)


@router.delete("/{borda_id}", response_model=SuccessMessage)
async def delete_borda(
    borda_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Delete a borda."""
    old_item = await borda_service.get_borda(db, user_id=user.id, borda_id=borda_id)
    await borda_service.delete_borda(db, user_id=user.id, borda_id=borda_id)

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="delete",
        resource="bordas",
        resource_id=borda_id,
        old_data=old_item,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="delete_borda",
        metadata={"borda_id": borda_id},
    )

    return SuccessMessage(message="Borda deleted successfully.")
