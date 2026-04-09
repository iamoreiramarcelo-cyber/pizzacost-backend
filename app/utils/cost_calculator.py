"""Server-side cost calculation engine for PizzaCost Pro.

This module replicates and replaces the client-side pizza/combo cost
calculations, ensuring a single source of truth on the backend.
"""

from __future__ import annotations

from app.utils.unit_conversion import calculate_ingredient_cost


def _sum_ingredient_costs(
    ingredientes: list[dict],
    insumos_map: dict[str, dict],
) -> float:
    """Sum costs for a list of ingredient entries.

    Each ingredient dict is expected to have:
        - insumo_id: str  (key into insumos_map)
        - quantidade: float
        - unidade: str | None  (if None, falls back to the insumo's base unit)

    Each insumo in insumos_map is expected to have:
        - custo_unitario: float
        - unidade: str
    """
    total = 0.0
    for ing in ingredientes:
        insumo_id = str(ing["insumo_id"])
        insumo = insumos_map[insumo_id]
        # When unidade is None, fall back to the insumo's base unit
        unidade_uso = ing.get("unidade") or insumo["unidade"]
        total += calculate_ingredient_cost(
            quantidade=float(ing["quantidade"]),
            unidade_uso=unidade_uso,
            insumo_custo_unitario=float(insumo["custo_unitario"]),
            insumo_unidade=insumo["unidade"],
        )
    return total


def calculate_pizza_cost(
    pizza_ingredientes: list[dict],
    custo_adicionais: float,
    tamanho: dict,
    borda: dict | None,
    insumos_map: dict[str, dict],
) -> float:
    """Calculate the total cost of a single pizza.

    Args:
        pizza_ingredientes: List of ingredient dicts for the pizza.
        custo_adicionais: Extra costs (gas, labour, etc.).
        tamanho: Size dict with keys ``custo_embalagem`` and ``custo_massa``.
        borda: Optional crust dict with key ``ingredientes`` (list of ingredient
               dicts). Pass ``None`` if no special crust.
        insumos_map: Lookup of insumo_id -> insumo details (custo_unitario,
                     unidade).

    Returns:
        Total pizza cost rounded to 2 decimal places.
    """
    total = 0.0

    # Ingredient costs
    total += _sum_ingredient_costs(pizza_ingredientes, insumos_map)

    # Size-related costs
    total += float(tamanho.get("custo_embalagem", 0))
    total += float(tamanho.get("custo_massa", 0))

    # Crust (borda) ingredient costs
    if borda is not None:
        borda_ingredientes = borda.get("ingredientes", [])
        total += _sum_ingredient_costs(borda_ingredientes, insumos_map)

    # Additional costs
    total += custo_adicionais

    return round(total, 2)


def calculate_combo_cost(
    combo_pizzas: list[dict],
    outros_custos: float,
    pizzas_map: dict[str, float],
) -> float:
    """Calculate the total cost of a combo.

    Args:
        combo_pizzas: List of dicts, each with ``pizza_id`` and ``quantidade``.
        outros_custos: Additional costs beyond the pizzas themselves.
        pizzas_map: Lookup of pizza_id -> pre-calculated pizza cost.

    Returns:
        Total combo cost rounded to 2 decimal places.
    """
    total = 0.0
    for entry in combo_pizzas:
        pizza_id = str(entry["pizza_id"])
        quantidade = float(entry.get("quantidade", 1))
        total += pizzas_map[pizza_id] * quantidade

    total += outros_custos
    return round(total, 2)


def calculate_profit_margin(
    custo: float,
    preco_venda: float | None,
) -> float | None:
    """Calculate profit margin as a percentage of the selling price.

    Args:
        custo: The total cost.
        preco_venda: The selling price. May be ``None`` or ``0``.

    Returns:
        Profit margin percentage rounded to 1 decimal place, or ``None``
        if the selling price is unavailable or zero.
    """
    if preco_venda is None or preco_venda == 0:
        return None
    margin = ((preco_venda - custo) / preco_venda) * 100
    return round(margin, 1)
