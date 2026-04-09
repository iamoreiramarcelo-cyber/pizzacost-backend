"""Pizza (flavor / recipe) service for PizzaCost Pro."""

from __future__ import annotations

import logging

from supabase import Client

from app.exceptions import not_found, validation_error
from app.utils.cost_calculator import calculate_pizza_cost
from app.utils.sanitize import sanitize_string

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_insumos_map(db: Client, user_id: str, insumo_ids: list[str]) -> dict[str, dict]:
    """Fetch insumos by IDs and return a lookup dict."""
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


def _serialize_ingredientes(ingredientes: list[dict]) -> list[dict]:
    """Normalise ingredient dicts for JSON storage."""
    return [
        {
            "insumo_id": str(ing["insumo_id"]),
            "quantidade": float(ing["quantidade"]),
            "unidade": ing.get("unidade"),
        }
        for ing in ingredientes
    ]


def _collect_insumo_ids(pizza_ingredientes: list[dict], borda: dict | None) -> list[str]:
    """Gather all unique insumo IDs from pizza ingredients and borda."""
    ids = {str(ing["insumo_id"]) for ing in pizza_ingredientes}
    if borda:
        for ing in borda.get("ingredientes", []):
            ids.add(str(ing["insumo_id"]))
    return list(ids)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def list_pizzas(
    db: Client,
    user_id: str,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """Return a paginated list of pizzas for the user."""
    offset = (page - 1) * per_page

    count_result = (
        db.table("pizzas")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    total = count_result.count or 0

    result = (
        db.table("pizzas")
        .select("*")
        .eq("user_id", user_id)
        .order("nome")
        .range(offset, offset + per_page - 1)
        .execute()
    )
    return result.data, total


async def get_pizza(db: Client, user_id: str, pizza_id: str) -> dict:
    """Fetch a single pizza by ID, scoped to user."""
    result = (
        db.table("pizzas")
        .select("*")
        .eq("id", pizza_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise not_found("Pizza")
    return result.data[0]


async def get_pizza_with_details(db: Client, user_id: str, pizza_id: str) -> dict:
    """Return a pizza with resolved ingredient names, tamanho name, and borda name."""
    pizza = await get_pizza(db, user_id, pizza_id)

    # Resolve tamanho
    tamanho_result = (
        db.table("tamanhos")
        .select("nome, custo_embalagem, custo_massa")
        .eq("id", pizza["tamanho_id"])
        .eq("user_id", user_id)
        .execute()
    )
    pizza["tamanho"] = tamanho_result.data[0] if tamanho_result.data else None

    # Resolve borda
    borda_id = pizza.get("borda_id")
    if borda_id:
        borda_result = (
            db.table("bordas")
            .select("nome, custo_calculado")
            .eq("id", borda_id)
            .eq("user_id", user_id)
            .execute()
        )
        pizza["borda"] = borda_result.data[0] if borda_result.data else None
    else:
        pizza["borda"] = None

    # Resolve ingredient names
    ingredientes = pizza.get("ingredientes", [])
    insumo_ids = [str(ing["insumo_id"]) for ing in ingredientes]
    insumos_map = _build_insumos_map(db, user_id, insumo_ids)
    enriched = []
    for ing in ingredientes:
        insumo = insumos_map.get(str(ing["insumo_id"]), {})
        enriched.append(
            {
                **ing,
                "nome": insumo.get("nome", "Desconhecido"),
                "custo_unitario": insumo.get("custo_unitario"),
            }
        )
    pizza["ingredientes_detalhados"] = enriched

    return pizza


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def create_pizza(db: Client, user_id: str, data: dict) -> dict:
    """Create a new pizza with full cost calculation.

    Validates subscription limits and ownership of tamanho, borda, and insumos.
    """
    from app.services.subscription_service import check_limit

    await check_limit(db, user_id, "max_pizzas")

    tamanho_id = str(data["tamanho_id"])
    borda_id = str(data["borda_id"]) if data.get("borda_id") else None

    # Verify tamanho
    tamanho_result = (
        db.table("tamanhos")
        .select("*")
        .eq("id", tamanho_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not tamanho_result.data:
        raise validation_error("Tamanho not found or does not belong to user.")
    tamanho = tamanho_result.data[0]

    # Verify borda (optional)
    borda: dict | None = None
    if borda_id:
        borda_result = (
            db.table("bordas")
            .select("*")
            .eq("id", borda_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not borda_result.data:
            raise validation_error("Borda not found or does not belong to user.")
        borda = borda_result.data[0]

    # Prepare ingredients
    ingredientes = data["ingredientes"]
    ingredientes_dicts = [
        ing if isinstance(ing, dict) else ing.model_dump() for ing in ingredientes
    ]

    # Verify all insumos belong to user
    all_insumo_ids = _collect_insumo_ids(ingredientes_dicts, borda)
    insumos_map = _build_insumos_map(db, user_id, all_insumo_ids)
    if len(insumos_map) != len(set(all_insumo_ids)):
        missing = set(all_insumo_ids) - set(insumos_map.keys())
        raise validation_error(f"Insumos not found: {missing}")

    custo_adicionais = float(data.get("custo_adicionais", 0))

    custo_calculado = calculate_pizza_cost(
        pizza_ingredientes=ingredientes_dicts,
        custo_adicionais=custo_adicionais,
        tamanho=tamanho,
        borda=borda,
        insumos_map=insumos_map,
    )

    payload = {
        "user_id": user_id,
        "nome": sanitize_string(data["nome"]),
        "tamanho_id": tamanho_id,
        "borda_id": borda_id,
        "ingredientes": _serialize_ingredientes(ingredientes_dicts),
        "custo_adicionais": custo_adicionais,
        "custo_calculado": custo_calculado,
        "preco_venda": data.get("preco_venda"),
    }

    result = db.table("pizzas").insert(payload).execute()
    return result.data[0]


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

async def update_pizza(
    db: Client,
    user_id: str,
    pizza_id: str,
    data: dict,
) -> dict:
    """Update a pizza, recalculating cost and cascading to combos."""
    current = await get_pizza(db, user_id, pizza_id)

    update_payload: dict = {}
    if data.get("nome") is not None:
        update_payload["nome"] = sanitize_string(data["nome"])
    if data.get("preco_venda") is not None:
        update_payload["preco_venda"] = float(data["preco_venda"])
    if data.get("custo_adicionais") is not None:
        update_payload["custo_adicionais"] = float(data["custo_adicionais"])

    # Tamanho
    tamanho_id = str(data["tamanho_id"]) if data.get("tamanho_id") is not None else current["tamanho_id"]
    if data.get("tamanho_id") is not None:
        t_check = (
            db.table("tamanhos")
            .select("*")
            .eq("id", tamanho_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not t_check.data:
            raise validation_error("Tamanho not found or does not belong to user.")
        update_payload["tamanho_id"] = tamanho_id

    # Borda
    borda_id = current.get("borda_id")
    if "borda_id" in data:
        borda_id = str(data["borda_id"]) if data["borda_id"] else None
        if borda_id:
            b_check = (
                db.table("bordas")
                .select("*")
                .eq("id", borda_id)
                .eq("user_id", user_id)
                .execute()
            )
            if not b_check.data:
                raise validation_error("Borda not found or does not belong to user.")
        update_payload["borda_id"] = borda_id

    # Ingredients
    if data.get("ingredientes") is not None:
        ingredientes_dicts = [
            ing if isinstance(ing, dict) else ing.model_dump() for ing in data["ingredientes"]
        ]
        update_payload["ingredientes"] = _serialize_ingredientes(ingredientes_dicts)
    else:
        ingredientes_dicts = current.get("ingredientes", [])

    # Full recalculation
    tamanho = (
        db.table("tamanhos").select("*").eq("id", tamanho_id).eq("user_id", user_id).execute()
    ).data[0]

    borda: dict | None = None
    if borda_id:
        borda = (
            db.table("bordas").select("*").eq("id", borda_id).eq("user_id", user_id).execute()
        ).data[0]

    all_insumo_ids = _collect_insumo_ids(ingredientes_dicts, borda)
    insumos_map = _build_insumos_map(db, user_id, all_insumo_ids)

    custo_adicionais = float(
        update_payload.get("custo_adicionais", current.get("custo_adicionais", 0))
    )

    custo_calculado = calculate_pizza_cost(
        pizza_ingredientes=ingredientes_dicts,
        custo_adicionais=custo_adicionais,
        tamanho=tamanho,
        borda=borda,
        insumos_map=insumos_map,
    )
    update_payload["custo_calculado"] = custo_calculado

    result = (
        db.table("pizzas")
        .update(update_payload)
        .eq("id", pizza_id)
        .eq("user_id", user_id)
        .execute()
    )
    updated = result.data[0]

    # Cascade to combos
    await _cascade_pizza_cost(db, user_id, pizza_id)

    return updated


async def _recalculate_pizza_cost(db: Client, user_id: str, pizza_id: str) -> None:
    """Recalculate cost for a single pizza (called from cascade)."""
    pizza = await get_pizza(db, user_id, pizza_id)

    tamanho_id = pizza["tamanho_id"]
    borda_id = pizza.get("borda_id")
    ingredientes = pizza.get("ingredientes", [])

    tamanho = (
        db.table("tamanhos").select("*").eq("id", tamanho_id).eq("user_id", user_id).execute()
    ).data[0]

    borda: dict | None = None
    if borda_id:
        borda_result = (
            db.table("bordas").select("*").eq("id", borda_id).eq("user_id", user_id).execute()
        )
        borda = borda_result.data[0] if borda_result.data else None

    all_insumo_ids = _collect_insumo_ids(ingredientes, borda)
    insumos_map = _build_insumos_map(db, user_id, all_insumo_ids)

    custo = calculate_pizza_cost(
        pizza_ingredientes=ingredientes,
        custo_adicionais=float(pizza.get("custo_adicionais", 0)),
        tamanho=tamanho,
        borda=borda,
        insumos_map=insumos_map,
    )

    db.table("pizzas").update({"custo_calculado": custo}).eq("id", pizza_id).eq("user_id", user_id).execute()

    # Cascade further to combos
    await _cascade_pizza_cost(db, user_id, pizza_id)


async def _cascade_pizza_cost(db: Client, user_id: str, pizza_id: str) -> None:
    """Recalculate combos that include this pizza."""
    from app.services.combo_service import _recalculate_combo_cost

    combos_result = (
        db.table("combos")
        .select("id, pizzas")
        .eq("user_id", user_id)
        .execute()
    )
    for combo in combos_result.data:
        combo_pizzas = combo.get("pizzas", [])
        uses_pizza = any(str(p.get("pizza_id")) == pizza_id for p in combo_pizzas)
        if uses_pizza:
            await _recalculate_combo_cost(db, user_id, combo["id"])


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

async def delete_pizza(db: Client, user_id: str, pizza_id: str) -> None:
    """Delete a pizza. Raises if not found."""
    await get_pizza(db, user_id, pizza_id)
    db.table("pizzas").delete().eq("id", pizza_id).eq("user_id", user_id).execute()
