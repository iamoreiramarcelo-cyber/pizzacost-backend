"""Tamanho (pizza size) service for PizzaCost Pro."""

from __future__ import annotations

import logging

from supabase import Client

from app.exceptions import not_found, validation_error
from app.utils.sanitize import sanitize_string

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def list_tamanhos(
    db: Client,
    user_id: str,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """Return a paginated list of tamanhos for the given user."""
    offset = (page - 1) * per_page

    count_result = (
        db.table("tamanhos")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    total = count_result.count or 0

    result = (
        db.table("tamanhos")
        .select("*")
        .eq("user_id", user_id)
        .order("nome")
        .range(offset, offset + per_page - 1)
        .execute()
    )
    return result.data, total


async def get_tamanho(db: Client, user_id: str, tamanho_id: str) -> dict:
    """Fetch a single tamanho by ID, scoped to the user."""
    result = (
        db.table("tamanhos")
        .select("*")
        .eq("id", tamanho_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise not_found("Tamanho")
    return result.data[0]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def create_tamanho(db: Client, user_id: str, data: dict) -> dict:
    """Create a new tamanho, computing ``custo_embalagem``.

    Checks subscription limits before inserting.
    """
    from app.services.subscription_service import check_limit

    await check_limit(db, user_id, "max_tamanhos")

    nome = sanitize_string(data["nome"])
    preco_total = float(data["preco_total"])
    quantidade_embalagens = int(data["quantidade_embalagens"])
    if quantidade_embalagens <= 0:
        raise validation_error(
            "quantidade_embalagens must be greater than zero.",
            details=[{"field": "quantidade_embalagens", "message": "Must be > 0"}],
        )
    custo_massa = float(data["custo_massa"])
    custo_embalagem = round(preco_total / quantidade_embalagens, 4)

    payload = {
        "user_id": user_id,
        "nome": nome,
        "preco_total": preco_total,
        "quantidade_embalagens": quantidade_embalagens,
        "custo_massa": custo_massa,
        "custo_embalagem": custo_embalagem,
    }

    result = db.table("tamanhos").insert(payload).execute()
    return result.data[0]


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

async def update_tamanho(
    db: Client,
    user_id: str,
    tamanho_id: str,
    data: dict,
) -> dict:
    """Update a tamanho, recalculating ``custo_embalagem`` and cascading to pizzas."""
    current = await get_tamanho(db, user_id, tamanho_id)

    update_payload: dict = {}
    if data.get("nome") is not None:
        update_payload["nome"] = sanitize_string(data["nome"])
    if data.get("custo_massa") is not None:
        update_payload["custo_massa"] = float(data["custo_massa"])

    preco_total = (
        float(data["preco_total"])
        if data.get("preco_total") is not None
        else float(current["preco_total"])
    )
    qtd_embalagens = (
        int(data["quantidade_embalagens"])
        if data.get("quantidade_embalagens") is not None
        else int(current["quantidade_embalagens"])
    )

    if data.get("preco_total") is not None or data.get("quantidade_embalagens") is not None:
        if qtd_embalagens <= 0:
            raise validation_error(
                "quantidade_embalagens must be greater than zero.",
                details=[{"field": "quantidade_embalagens", "message": "Must be > 0"}],
            )
        update_payload["preco_total"] = preco_total
        update_payload["quantidade_embalagens"] = qtd_embalagens
        update_payload["custo_embalagem"] = round(preco_total / qtd_embalagens, 4)

    if not update_payload:
        return current

    result = (
        db.table("tamanhos")
        .update(update_payload)
        .eq("id", tamanho_id)
        .eq("user_id", user_id)
        .execute()
    )
    updated = result.data[0]

    # Cascade: recalculate all pizzas using this tamanho
    await _cascade_tamanho_cost(db, user_id, tamanho_id)

    return updated


async def _cascade_tamanho_cost(db: Client, user_id: str, tamanho_id: str) -> None:
    """Recalculate costs for all pizzas that use this tamanho."""
    from app.services.pizza_service import _recalculate_pizza_cost

    pizzas_result = (
        db.table("pizzas")
        .select("id")
        .eq("user_id", user_id)
        .eq("tamanho_id", tamanho_id)
        .execute()
    )
    for pizza in pizzas_result.data:
        await _recalculate_pizza_cost(db, user_id, pizza["id"])


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

async def delete_tamanho(db: Client, user_id: str, tamanho_id: str) -> None:
    """Delete a tamanho. Raises if not found."""
    await get_tamanho(db, user_id, tamanho_id)
    db.table("tamanhos").delete().eq("id", tamanho_id).eq("user_id", user_id).execute()
