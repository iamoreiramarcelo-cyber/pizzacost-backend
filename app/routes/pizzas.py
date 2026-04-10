"""Pizza routes for PizzaCost Pro."""

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.database import get_supabase_client
from app.middleware.auth import get_current_user, UserContext
from app.middleware.audit import audit_log
from app.models import (
    PaginatedResponse,
    PaginationMeta,
    PizzaCreate,
    PizzaResponse,
    PizzaUpdate,
    SuccessMessage,
)
from app.services import pizza_service, activity_service

router = APIRouter(prefix="/api/v1/pizzas", tags=["Pizzas"])


@router.get("", response_model=PaginatedResponse[PizzaResponse])
async def list_pizzas(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """List all pizzas for the authenticated user."""
    items, total = await pizza_service.list_pizzas(
        db, user_id=user.id, page=page, per_page=per_page
    )
    return PaginatedResponse(
        data=[PizzaResponse(**item) for item in items],
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
    )


@router.get("/{pizza_id}", response_model=PizzaResponse)
async def get_pizza(
    pizza_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Get a single pizza by ID."""
    item = await pizza_service.get_pizza(db, user_id=user.id, pizza_id=pizza_id)
    return PizzaResponse(**item)


@router.get("/{pizza_id}/details")
async def get_pizza_details(
    pizza_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Get a pizza with resolved ingredient names, tamanho, and borda details."""
    item = await pizza_service.get_pizza_with_details(
        db, user_id=user.id, pizza_id=pizza_id
    )
    return item


@router.post("", response_model=PizzaResponse, status_code=201)
async def create_pizza(
    body: PizzaCreate,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Create a new pizza. Checks subscription limit."""
    data = body.model_dump()
    data["tamanho_id"] = str(data["tamanho_id"])
    if data.get("border_id"):
        data["border_id"] = str(data["border_id"])
    else:
        data["border_id"] = None
    data["ingredientes"] = [
        ing if isinstance(ing, dict) else ing.model_dump()
        for ing in body.ingredientes
    ]

    item = await pizza_service.create_pizza(db, user_id=user.id, data=data)

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="create",
        resource="pizzas",
        resource_id=str(item["id"]),
        new_data=item,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="create_pizza",
        metadata={"pizza_id": str(item["id"]), "nome": item["nome"]},
    )

    return PizzaResponse(**item)


@router.put("/{pizza_id}", response_model=PizzaResponse)
async def update_pizza(
    pizza_id: str,
    body: PizzaUpdate,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Update an existing pizza."""
    data = body.model_dump(exclude_none=True)
    if "tamanho_id" in data:
        data["tamanho_id"] = str(data["tamanho_id"])
    if "border_id" in data:
        data["border_id"] = str(data["border_id"]) if data["border_id"] else None

    old_item = await pizza_service.get_pizza(db, user_id=user.id, pizza_id=pizza_id)
    item = await pizza_service.update_pizza(
        db, user_id=user.id, pizza_id=pizza_id, data=data
    )

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="update",
        resource="pizzas",
        resource_id=pizza_id,
        old_data=old_item,
        new_data=item,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="update_pizza",
        metadata={"pizza_id": pizza_id},
    )

    return PizzaResponse(**item)


@router.delete("/{pizza_id}", response_model=SuccessMessage)
async def delete_pizza(
    pizza_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Delete a pizza."""
    old_item = await pizza_service.get_pizza(db, user_id=user.id, pizza_id=pizza_id)
    await pizza_service.delete_pizza(db, user_id=user.id, pizza_id=pizza_id)

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="delete",
        resource="pizzas",
        resource_id=pizza_id,
        old_data=old_item,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="delete_pizza",
        metadata={"pizza_id": pizza_id},
    )

    return SuccessMessage(message="Pizza deleted successfully.")
