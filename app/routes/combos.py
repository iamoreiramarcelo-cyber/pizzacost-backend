"""Combo (pizza bundle) routes for PizzaCost Pro."""

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.database import get_supabase_client
from app.middleware.auth import get_current_user, UserContext
from app.middleware.audit import audit_log
from app.models import (
    ComboCreate,
    ComboResponse,
    ComboUpdate,
    PaginatedResponse,
    PaginationMeta,
    SuccessMessage,
)
from app.services import combo_service, activity_service

router = APIRouter(prefix="/api/v1/combos", tags=["Combos"])


@router.get("/", response_model=PaginatedResponse[ComboResponse])
async def list_combos(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """List all combos for the authenticated user."""
    items, total = await combo_service.list_combos(
        db, user_id=user.id, page=page, per_page=per_page
    )
    return PaginatedResponse(
        data=[ComboResponse(**item) for item in items],
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
    )


@router.get("/{combo_id}", response_model=ComboResponse)
async def get_combo(
    combo_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Get a single combo by ID."""
    item = await combo_service.get_combo(db, user_id=user.id, combo_id=combo_id)
    return ComboResponse(**item)


@router.post("/", response_model=ComboResponse, status_code=201)
async def create_combo(
    body: ComboCreate,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Create a new combo."""
    data = body.model_dump()
    # Map flavor_id -> pizza_id for the service layer
    data["pizzas"] = [
        {"pizza_id": str(p["flavor_id"]), "quantidade": p["quantidade"]}
        for p in data["pizzas"]
    ]
    # Keep preco_venda_sugerido as-is (matches DB column name)

    item = await combo_service.create_combo(db, user_id=user.id, data=data)

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="create",
        resource="combos",
        resource_id=str(item["id"]),
        new_data=item,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="create_combo",
        metadata={"combo_id": str(item["id"]), "nome": item["nome"]},
    )

    return ComboResponse(**item)


@router.put("/{combo_id}", response_model=ComboResponse)
async def update_combo(
    combo_id: str,
    body: ComboUpdate,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Update an existing combo."""
    data = body.model_dump(exclude_none=True)
    if "pizzas" in data:
        data["pizzas"] = [
            {"pizza_id": str(p["flavor_id"]), "quantidade": p["quantidade"]}
            for p in data["pizzas"]
        ]
    # preco_venda_sugerido already matches DB column name, no mapping needed

    old_item = await combo_service.get_combo(db, user_id=user.id, combo_id=combo_id)
    item = await combo_service.update_combo(
        db, user_id=user.id, combo_id=combo_id, data=data
    )

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="update",
        resource="combos",
        resource_id=combo_id,
        old_data=old_item,
        new_data=item,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="update_combo",
        metadata={"combo_id": combo_id},
    )

    return ComboResponse(**item)


@router.delete("/{combo_id}", response_model=SuccessMessage)
async def delete_combo(
    combo_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Delete a combo."""
    old_item = await combo_service.get_combo(db, user_id=user.id, combo_id=combo_id)
    await combo_service.delete_combo(db, user_id=user.id, combo_id=combo_id)

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="delete",
        resource="combos",
        resource_id=combo_id,
        old_data=old_item,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="delete_combo",
        metadata={"combo_id": combo_id},
    )

    return SuccessMessage(message="Combo deleted successfully.")
