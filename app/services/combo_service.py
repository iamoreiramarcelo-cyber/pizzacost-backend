"""Combo service for PizzaCost Pro."""

from __future__ import annotations

import logging

from supabase import Client

from app.exceptions import not_found, validation_error
from app.utils.cost_calculator import calculate_combo_cost
from app.utils.sanitize import sanitize_string

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_pizzas_cost_map(db: Client, user_id: str, pizza_ids: list[str]) -> dict[str, float]:
    """Fetch pizzas by IDs and return a dict of pizza_id -> custo_calculado."""
    if not pizza_ids:
        return {}
    result = (
        db.table("pizzas")
        .select("id, custo_calculado")
        .eq("user_id", user_id)
        .in_("id", pizza_ids)
        .execute()
    )
    return {str(row["id"]): float(row["custo_calculado"]) for row in result.data}


def _serialize_combo_pizzas(pizzas: list[dict]) -> list[dict]:
    """Normalise combo pizza entries for JSON storage."""
    return [
        {
            "pizza_id": str(p["pizza_id"]),
            "quantidade": int(p.get("quantidade", 1)),
        }
        for p in pizzas
    ]


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def list_combos(
    db: Client,
    user_id: str,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """Return a paginated list of combos for the user."""
    offset = (page - 1) * per_page

    count_result = (
        db.table("combos")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    total = count_result.count or 0

    result = (
        db.table("combos")
        .select("*")
        .eq("user_id", user_id)
        .order("nome")
        .range(offset, offset + per_page - 1)
        .execute()
    )
    return result.data, total


async def get_combo(db: Client, user_id: str, combo_id: str) -> dict:
    """Fetch a single combo by ID, scoped to user."""
    result = (
        db.table("combos")
        .select("*")
        .eq("id", combo_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise not_found("Combo")
    return result.data[0]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def create_combo(db: Client, user_id: str, data: dict) -> dict:
    """Create a new combo, calculating total cost from included pizzas.

    Validates subscription limits and that all referenced pizza IDs belong to the user.
    """
    from app.services.subscription_service import check_limit

    await check_limit(db, user_id, "max_combos")

    combo_pizzas = data["pizzas"]
    combo_pizzas_dicts = [
        p if isinstance(p, dict) else p.model_dump() for p in combo_pizzas
    ]
    pizza_ids = list({str(p["pizza_id"]) for p in combo_pizzas_dicts})

    # Verify all pizzas belong to user
    pizzas_map = _build_pizzas_cost_map(db, user_id, pizza_ids)
    if len(pizzas_map) != len(pizza_ids):
        missing = set(pizza_ids) - set(pizzas_map.keys())
        raise validation_error(f"Pizzas not found: {missing}")

    outros_custos = float(data.get("outros_custos", 0))

    custo_calculado = calculate_combo_cost(
        combo_pizzas=combo_pizzas_dicts,
        outros_custos=outros_custos,
        pizzas_map=pizzas_map,
    )

    payload = {
        "user_id": user_id,
        "nome": sanitize_string(data["nome"]),
        "pizzas": _serialize_combo_pizzas(combo_pizzas_dicts),
        "outros_custos": outros_custos,
        "custo_calculado": custo_calculado,
        "preco_venda": data.get("preco_venda"),
    }

    result = db.table("combos").insert(payload).execute()
    return result.data[0]


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

async def update_combo(
    db: Client,
    user_id: str,
    combo_id: str,
    data: dict,
) -> dict:
    """Update a combo, recalculating total cost."""
    current = await get_combo(db, user_id, combo_id)

    update_payload: dict = {}
    if data.get("nome") is not None:
        update_payload["nome"] = sanitize_string(data["nome"])
    if data.get("preco_venda") is not None:
        update_payload["preco_venda"] = float(data["preco_venda"])
    if data.get("outros_custos") is not None:
        update_payload["outros_custos"] = float(data["outros_custos"])

    # Pizzas
    if data.get("pizzas") is not None:
        combo_pizzas_dicts = [
            p if isinstance(p, dict) else p.model_dump() for p in data["pizzas"]
        ]
        update_payload["pizzas"] = _serialize_combo_pizzas(combo_pizzas_dicts)
    else:
        combo_pizzas_dicts = current.get("pizzas", [])

    pizza_ids = list({str(p["pizza_id"]) for p in combo_pizzas_dicts})
    pizzas_map = _build_pizzas_cost_map(db, user_id, pizza_ids)
    if len(pizzas_map) != len(pizza_ids):
        missing = set(pizza_ids) - set(pizzas_map.keys())
        raise validation_error(f"Pizzas not found: {missing}")

    outros_custos = float(
        update_payload.get("outros_custos", current.get("outros_custos", 0))
    )

    custo_calculado = calculate_combo_cost(
        combo_pizzas=combo_pizzas_dicts,
        outros_custos=outros_custos,
        pizzas_map=pizzas_map,
    )
    update_payload["custo_calculado"] = custo_calculado

    result = (
        db.table("combos")
        .update(update_payload)
        .eq("id", combo_id)
        .eq("user_id", user_id)
        .execute()
    )
    return result.data[0]


async def _recalculate_combo_cost(db: Client, user_id: str, combo_id: str) -> None:
    """Recalculate cost for a single combo (called from cascade)."""
    combo = await get_combo(db, user_id, combo_id)
    combo_pizzas = combo.get("pizzas", [])
    pizza_ids = list({str(p["pizza_id"]) for p in combo_pizzas})
    pizzas_map = _build_pizzas_cost_map(db, user_id, pizza_ids)
    outros_custos = float(combo.get("outros_custos", 0))

    custo = calculate_combo_cost(
        combo_pizzas=combo_pizzas,
        outros_custos=outros_custos,
        pizzas_map=pizzas_map,
    )
    db.table("combos").update({"custo_calculado": custo}).eq("id", combo_id).eq("user_id", user_id).execute()


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

async def delete_combo(db: Client, user_id: str, combo_id: str) -> None:
    """Delete a combo. Raises if not found."""
    await get_combo(db, user_id, combo_id)
    db.table("combos").delete().eq("id", combo_id).eq("user_id", user_id).execute()
