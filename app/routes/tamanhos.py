"""Tamanho (pizza size) routes for PizzaCost Pro."""

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.database import get_supabase_client
from app.middleware.auth import get_current_user, UserContext
from app.middleware.audit import audit_log
from app.models import (
    PaginatedResponse,
    PaginationMeta,
    SuccessMessage,
    TamanhoCreate,
    TamanhoResponse,
    TamanhoUpdate,
)
from app.services import tamanho_service, activity_service

router = APIRouter(prefix="/api/v1/tamanhos", tags=["Tamanhos"])


@router.get("/", response_model=PaginatedResponse[TamanhoResponse])
async def list_tamanhos(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """List all pizza sizes for the authenticated user."""
    items, total = await tamanho_service.list_tamanhos(
        db, user_id=user.id, page=page, per_page=per_page
    )
    return PaginatedResponse(
        data=[TamanhoResponse(**item) for item in items],
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
    )


@router.get("/{tamanho_id}", response_model=TamanhoResponse)
async def get_tamanho(
    tamanho_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Get a single pizza size by ID."""
    item = await tamanho_service.get_tamanho(db, user_id=user.id, tamanho_id=tamanho_id)
    return TamanhoResponse(**item)


@router.post("/", response_model=TamanhoResponse, status_code=201)
async def create_tamanho(
    body: TamanhoCreate,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Create a new pizza size. Checks subscription limit."""
    data = body.model_dump()
    item = await tamanho_service.create_tamanho(db, user_id=user.id, data=data)

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="create",
        resource="tamanhos",
        resource_id=str(item["id"]),
        new_data=item,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="create_tamanho",
        metadata={"tamanho_id": str(item["id"]), "nome": item["nome"]},
    )

    return TamanhoResponse(**item)


@router.put("/{tamanho_id}", response_model=TamanhoResponse)
async def update_tamanho(
    tamanho_id: str,
    body: TamanhoUpdate,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Update an existing pizza size."""
    data = body.model_dump(exclude_none=True)

    old_item = await tamanho_service.get_tamanho(db, user_id=user.id, tamanho_id=tamanho_id)
    item = await tamanho_service.update_tamanho(
        db, user_id=user.id, tamanho_id=tamanho_id, data=data
    )

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="update",
        resource="tamanhos",
        resource_id=tamanho_id,
        old_data=old_item,
        new_data=item,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="update_tamanho",
        metadata={"tamanho_id": tamanho_id},
    )

    return TamanhoResponse(**item)


@router.delete("/{tamanho_id}", response_model=SuccessMessage)
async def delete_tamanho(
    tamanho_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Delete a pizza size."""
    old_item = await tamanho_service.get_tamanho(db, user_id=user.id, tamanho_id=tamanho_id)
    await tamanho_service.delete_tamanho(db, user_id=user.id, tamanho_id=tamanho_id)

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="delete",
        resource="tamanhos",
        resource_id=tamanho_id,
        old_data=old_item,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="delete_tamanho",
        metadata={"tamanho_id": tamanho_id},
    )

    return SuccessMessage(message="Tamanho deleted successfully.")
