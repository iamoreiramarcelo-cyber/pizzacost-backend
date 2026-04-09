"""User dashboard service for PizzaCost Pro."""

from __future__ import annotations

import logging

from supabase import Client

logger = logging.getLogger(__name__)


async def get_user_dashboard(db: Client, user_id: str) -> dict:
    """Return a dashboard summary for a regular user.

    Returns a dict with:
        - ``counts``: number of insumos, tamanhos, bordas, pizzas, combos
        - ``top_pizzas``: top 5 most expensive pizzas
        - ``top_combos``: top 5 most expensive combos
        - ``total_ingredient_spending``: estimated total spending on ingredients
    """
    # --- Counts -----------------------------------------------------------
    tables = ["insumos", "tamanhos", "bordas", "pizzas", "combos"]
    counts: dict[str, int] = {}
    for table in tables:
        result = (
            db.table(table)
            .select("id", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        counts[table] = result.count or 0

    # --- Top 5 pizzas by cost ---------------------------------------------
    top_pizzas_result = (
        db.table("pizzas")
        .select("id, nome, custo_calculado, preco_venda")
        .eq("user_id", user_id)
        .order("custo_calculado", desc=True)
        .range(0, 4)
        .execute()
    )
    top_pizzas = top_pizzas_result.data

    # --- Top 5 combos by cost ---------------------------------------------
    top_combos_result = (
        db.table("combos")
        .select("id, nome, custo_calculado, preco_venda")
        .eq("user_id", user_id)
        .order("custo_calculado", desc=True)
        .range(0, 4)
        .execute()
    )
    top_combos = top_combos_result.data

    # --- Total ingredient spending estimate --------------------------------
    # Sum preco for all insumos (total cost of purchased ingredients)
    insumos_result = (
        db.table("insumos")
        .select("preco")
        .eq("user_id", user_id)
        .execute()
    )
    total_ingredient_spending = round(
        sum(float(row["preco"]) for row in insumos_result.data), 2
    )

    return {
        "counts": counts,
        "top_pizzas": top_pizzas,
        "top_combos": top_combos,
        "total_ingredient_spending": total_ingredient_spending,
    }
