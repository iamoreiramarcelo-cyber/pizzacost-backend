"""Borda (pizza crust / border) service for PizzaCost Pro."""

from __future__ import annotations

import logging

from supabase import Client

from app.exceptions import not_found, validation_error
from app.utils.sanitize import sanitize_string
from app.utils.unit_conversion import calculate_ingredient_cost

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_insumos_map(db: Client, user_id: str, insumo_ids: list[str]) -> dict[str, dict]:
    """Fetch insumos by IDs and return a dict keyed by insumo_id."""
    if not insumo_ids:
        return {}
    result = (
        db.table("insumos")
        .select("id, custo_unitario, unidade, nome")
        .eq("user_id", user_id)
        .in_("id", insumo_ids)
        .execute()
    )
    return {str(row["id"]): row for row in result.data}


def _calculate_borda_cost(ingredientes: list[dict], insumos_map: dict[str, dict]) -> float:
    """Calculate total cost of borda ingredients."""
    total = 0.0
    for ing in ingredientes:
        insumo_id = str(ing["insumo_id"])
        insumo = insumos_map.get(insumo_id)
        if insumo is None:
            raise validation_error(
                f"Insumo {insumo_id} not found.",
                details=[{"field": "ingredientes", "message": f"Insumo {insumo_id} not found"}],
            )
        unidade_uso = ing.get("unidade") or insumo["unidade"]
        total += calculate_ingredient_cost(
            quantidade=float(ing["quantidade"]),
            unidade_uso=unidade_uso,
            insumo_custo_unitario=float(insumo["custo_unitario"]),
            insumo_unidade=insumo["unidade"],
        )
    return round(total, 2)


def _serialize_ingredientes(ingredientes: list[dict]) -> list[dict]:
    """Ensure ingredient dicts are JSON-serialisable for storage."""
    return [
        {
            "insumo_id": str(ing["insumo_id"]),
            "quantidade": float(ing["quantidade"]),
            "unidade": ing.get("unidade"),
        }
        for ing in ingredientes
    ]


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def list_bordas(
    db: Client,
    user_id: str,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """Return a paginated list of bordas for the user."""
    offset = (page - 1) * per_page

    count_result = (
        db.table("bordas")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    total = count_result.count or 0

    result = (
        db.table("bordas")
        .select("*")
        .eq("user_id", user_id)
        .order("nome")
        .range(offset, offset + per_page - 1)
        .execute()
    )
    return result.data, total


async def get_borda(db: Client, user_id: str, borda_id: str) -> dict:
    """Fetch a single borda by ID, scoped to user."""
    result = (
        db.table("bordas")
        .select("*")
        .eq("id", borda_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise not_found("Borda")
    return result.data[0]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def create_borda(db: Client, user_id: str, data: dict) -> dict:
    """Create a new borda, calculating its cost from ingredients.

    Validates subscription limits and ownership of the tamanho and insumos.
    """
    from app.services.subscription_service import check_limit

    await check_limit(db, user_id, "max_bordas")

    tamanho_id = str(data["tamanho_id"])

    # Verify tamanho belongs to user
    tamanho_check = (
        db.table("tamanhos")
        .select("id")
        .eq("id", tamanho_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not tamanho_check.data:
        raise validation_error("Tamanho not found or does not belong to user.")

    ingredientes = data["ingredientes"]
    # Ensure ingredientes are dicts (may come as Pydantic models)
    ingredientes_dicts = [
        ing if isinstance(ing, dict) else ing.model_dump() for ing in ingredientes
    ]
    insumo_ids = [str(ing["insumo_id"]) for ing in ingredientes_dicts]

    # Verify all insumos belong to user
    insumos_map = _build_insumos_map(db, user_id, insumo_ids)
    if len(insumos_map) != len(set(insumo_ids)):
        missing = set(insumo_ids) - set(insumos_map.keys())
        raise validation_error(f"Insumos not found: {missing}")

    custo_calculado = _calculate_borda_cost(ingredientes_dicts, insumos_map)

    payload = {
        "user_id": user_id,
        "nome": sanitize_string(data["nome"]),
        "tamanho_id": tamanho_id,
        "preco_venda": data.get("preco_venda"),
        "ingredientes": _serialize_ingredientes(ingredientes_dicts),
        "custo_calculado": custo_calculado,
    }

    result = db.table("bordas").insert(payload).execute()
    return result.data[0]


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

async def update_borda(
    db: Client,
    user_id: str,
    borda_id: str,
    data: dict,
) -> dict:
    """Update a borda, recalculating cost and cascading to pizzas."""
    current = await get_borda(db, user_id, borda_id)

    update_payload: dict = {}
    if data.get("nome") is not None:
        update_payload["nome"] = sanitize_string(data["nome"])
    if data.get("preco_venda") is not None:
        update_payload["preco_venda"] = float(data["preco_venda"])

    # Tamanho change
    tamanho_id = str(data["tamanho_id"]) if data.get("tamanho_id") is not None else current["tamanho_id"]
    if data.get("tamanho_id") is not None:
        tamanho_check = (
            db.table("tamanhos")
            .select("id")
            .eq("id", tamanho_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not tamanho_check.data:
            raise validation_error("Tamanho not found or does not belong to user.")
        update_payload["tamanho_id"] = tamanho_id

    # Ingredients change
    ingredientes = data.get("ingredientes")
    if ingredientes is not None:
        ingredientes_dicts = [
            ing if isinstance(ing, dict) else ing.model_dump() for ing in ingredientes
        ]
        insumo_ids = [str(ing["insumo_id"]) for ing in ingredientes_dicts]
        insumos_map = _build_insumos_map(db, user_id, insumo_ids)
        if len(insumos_map) != len(set(insumo_ids)):
            missing = set(insumo_ids) - set(insumos_map.keys())
            raise validation_error(f"Insumos not found: {missing}")

        custo_calculado = _calculate_borda_cost(ingredientes_dicts, insumos_map)
        update_payload["ingredientes"] = _serialize_ingredientes(ingredientes_dicts)
        update_payload["custo_calculado"] = custo_calculado
    else:
        # Recalculate with existing ingredients (insumo prices may have changed)
        ingredientes_dicts = current.get("ingredientes", [])
        insumo_ids = [str(ing["insumo_id"]) for ing in ingredientes_dicts]
        if insumo_ids:
            insumos_map = _build_insumos_map(db, user_id, insumo_ids)
            custo_calculado = _calculate_borda_cost(ingredientes_dicts, insumos_map)
            update_payload["custo_calculado"] = custo_calculado

    if not update_payload:
        return current

    result = (
        db.table("bordas")
        .update(update_payload)
        .eq("id", borda_id)
        .eq("user_id", user_id)
        .execute()
    )
    updated = result.data[0]

    # Cascade: recalculate all pizzas that use this borda
    await _cascade_borda_cost(db, user_id, borda_id)

    return updated


async def _recalculate_borda_cost(db: Client, user_id: str, borda_id: str) -> None:
    """Recalculate cost for a single borda (called from cascade)."""
    borda = await get_borda(db, user_id, borda_id)
    ingredientes = borda.get("ingredientes", [])
    insumo_ids = [str(ing["insumo_id"]) for ing in ingredientes]
    if not insumo_ids:
        return
    insumos_map = _build_insumos_map(db, user_id, insumo_ids)
    custo = _calculate_borda_cost(ingredientes, insumos_map)
    db.table("bordas").update({"custo_calculado": custo}).eq("id", borda_id).eq("user_id", user_id).execute()


async def _cascade_borda_cost(db: Client, user_id: str, borda_id: str) -> None:
    """Recalculate pizzas that use this borda."""
    from app.services.pizza_service import _recalculate_pizza_cost

    pizzas_result = (
        db.table("pizzas")
        .select("id")
        .eq("user_id", user_id)
        .eq("borda_id", borda_id)
        .execute()
    )
    for pizza in pizzas_result.data:
        await _recalculate_pizza_cost(db, user_id, pizza["id"])


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

async def delete_borda(db: Client, user_id: str, borda_id: str) -> None:
    """Delete a borda. Raises if not found."""
    await get_borda(db, user_id, borda_id)
    db.table("bordas").delete().eq("id", borda_id).eq("user_id", user_id).execute()
