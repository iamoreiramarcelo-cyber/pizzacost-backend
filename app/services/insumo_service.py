"""Insumo (supply / ingredient) service for PizzaCost Pro."""

from __future__ import annotations

import logging

from supabase import Client

from app.exceptions import not_found, validation_error
from app.utils.sanitize import sanitize_string

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def list_insumos(
    db: Client,
    user_id: str,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """Return a paginated list of insumos for the given user.

    Returns:
        A tuple of ``(items, total_count)``.
    """
    offset = (page - 1) * per_page

    # Total count
    count_result = (
        db.table("insumos")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    total = count_result.count or 0

    # Paginated data
    result = (
        db.table("insumos")
        .select("*")
        .eq("user_id", user_id)
        .order("nome")
        .range(offset, offset + per_page - 1)
        .execute()
    )
    return result.data, total


async def get_insumo(db: Client, user_id: str, insumo_id: str) -> dict:
    """Fetch a single insumo by ID, scoped to the user.

    Raises:
        AppException: If not found.
    """
    result = (
        db.table("insumos")
        .select("*")
        .eq("id", insumo_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise not_found("Insumo")
    return result.data[0]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def create_insumo(db: Client, user_id: str, data: dict) -> dict:
    """Create a new insumo and compute ``custo_unitario``.

    Checks subscription limits before inserting.

    Args:
        data: Dict with keys ``nome``, ``unidade``, ``preco``,
              ``quantidade_comprada``.

    Returns:
        The newly-created insumo dict.
    """
    from app.services.subscription_service import check_limit

    await check_limit(db, user_id, "max_ingredients")

    nome = sanitize_string(data["nome"])
    preco = float(data["preco"])
    quantidade_comprada = float(data["quantidade_comprada"])
    if quantidade_comprada <= 0:
        raise validation_error(
            "quantidade_comprada must be greater than zero.",
            details=[{"field": "quantidade_comprada", "message": "Must be > 0"}],
        )
    custo_unitario = round(preco / quantidade_comprada, 4)

    payload = {
        "user_id": user_id,
        "nome": nome,
        "unidade": data["unidade"],
        "preco": preco,
        "quantidade_comprada": quantidade_comprada,
        "custo_unitario": custo_unitario,
    }

    result = db.table("insumos").insert(payload).execute()
    return result.data[0]


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

async def update_insumo(
    db: Client,
    user_id: str,
    insumo_id: str,
    data: dict,
) -> dict:
    """Update an existing insumo, recalculating ``custo_unitario`` if needed.

    After the update, triggers a cost cascade for all bordas and pizzas that
    reference this insumo.
    """
    # Fetch current to merge fields
    current = await get_insumo(db, user_id, insumo_id)

    update_payload: dict = {}
    if "nome" in data and data["nome"] is not None:
        update_payload["nome"] = sanitize_string(data["nome"])
    if "unidade" in data and data["unidade"] is not None:
        update_payload["unidade"] = data["unidade"]

    # Recalculate custo_unitario when price or quantity changes
    preco = float(data["preco"]) if data.get("preco") is not None else float(current["preco"])
    qtd = (
        float(data["quantidade_comprada"])
        if data.get("quantidade_comprada") is not None
        else float(current["quantidade_comprada"])
    )

    if data.get("preco") is not None or data.get("quantidade_comprada") is not None:
        if qtd <= 0:
            raise validation_error(
                "quantidade_comprada must be greater than zero.",
                details=[{"field": "quantidade_comprada", "message": "Must be > 0"}],
            )
        update_payload["preco"] = preco
        update_payload["quantidade_comprada"] = qtd
        update_payload["custo_unitario"] = round(preco / qtd, 4)

    if not update_payload:
        return current

    result = (
        db.table("insumos")
        .update(update_payload)
        .eq("id", insumo_id)
        .eq("user_id", user_id)
        .execute()
    )
    updated_insumo = result.data[0]

    # --- Cost cascade -----------------------------------------------------
    await _cascade_insumo_cost(db, user_id, insumo_id)

    return updated_insumo


async def _cascade_insumo_cost(db: Client, user_id: str, insumo_id: str) -> None:
    """Recalculate costs for all bordas and pizzas that use this insumo.

    Also recalculates pizzas that reference affected bordas, since pizza cost
    calculation re-derives borda ingredient costs from raw ingredients.
    """
    from app.services.borda_service import _recalculate_borda_cost
    from app.services.pizza_service import _recalculate_pizza_cost

    # Bordas that reference this insumo (JSONB contains)
    affected_borda_ids: set[str] = set()
    bordas_result = (
        db.table("bordas")
        .select("id, ingredientes")
        .eq("user_id", user_id)
        .execute()
    )
    for borda in bordas_result.data:
        ingredientes = borda.get("ingredientes", [])
        uses_insumo = any(
            str(ing.get("insumo_id")) == insumo_id for ing in ingredientes
        )
        if uses_insumo:
            affected_borda_ids.add(str(borda["id"]))
            await _recalculate_borda_cost(db, user_id, borda["id"])

    # Pizzas that reference this insumo directly in their ingredients
    pizza_ids_to_recalculate: set[str] = set()
    pizzas_result = (
        db.table("pizzas")
        .select("id, ingredientes, borda_id")
        .eq("user_id", user_id)
        .execute()
    )
    for pizza in pizzas_result.data:
        ingredientes = pizza.get("ingredientes", [])
        uses_insumo = any(
            str(ing.get("insumo_id")) == insumo_id for ing in ingredientes
        )
        # Also recalculate if the pizza uses an affected borda
        uses_affected_borda = (
            pizza.get("borda_id") is not None
            and str(pizza["borda_id"]) in affected_borda_ids
        )
        if uses_insumo or uses_affected_borda:
            pizza_ids_to_recalculate.add(str(pizza["id"]))

    for pizza_id in pizza_ids_to_recalculate:
        await _recalculate_pizza_cost(db, user_id, pizza_id)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

async def delete_insumo(db: Client, user_id: str, insumo_id: str) -> None:
    """Delete an insumo. Raises if not found."""
    # Verify ownership
    await get_insumo(db, user_id, insumo_id)

    db.table("insumos").delete().eq("id", insumo_id).eq("user_id", user_id).execute()
