"""Unit conversion utilities for PizzaCost Pro."""

from typing import Callable

# Each entry maps (from_unit, to_unit) -> conversion function
CONVERSION_MAP: dict[tuple[str, str], Callable[[float], float]] = {
    ("g", "kg"): lambda q: q / 1000,
    ("kg", "g"): lambda q: q * 1000,
    ("ml", "L"): lambda q: q / 1000,
    ("L", "ml"): lambda q: q * 1000,
}


def convert_quantity(quantity: float, from_unit: str, to_unit: str) -> float:
    """Convert a quantity between compatible units.

    Args:
        quantity: The numeric value to convert.
        from_unit: The source unit (e.g. "g", "kg", "ml", "L").
        to_unit: The target unit.

    Returns:
        The converted quantity.

    Raises:
        ValueError: If the conversion between the given units is not supported.
    """
    if from_unit == to_unit:
        return quantity

    key = (from_unit, to_unit)
    converter = CONVERSION_MAP.get(key)
    if converter is None:
        raise ValueError(
            f"Conversao de '{from_unit}' para '{to_unit}' nao e suportada."
        )
    return converter(quantity)


def calculate_ingredient_cost(
    quantidade: float,
    unidade_uso: str,
    insumo_custo_unitario: float,
    insumo_unidade: str,
) -> float:
    """Calculate the cost of an ingredient based on usage quantity and unit price.

    Converts the usage quantity to the insumo's base unit when the units
    differ, then multiplies by the unit cost.

    Args:
        quantidade: How much of the ingredient is used.
        unidade_uso: The unit in which the ingredient is measured for usage
                     (e.g. "g").
        insumo_custo_unitario: Cost per one unit of the insumo in its base
                               unit.
        insumo_unidade: The base unit of the insumo (e.g. "kg").

    Returns:
        The total cost for this ingredient usage.
    """
    quantidade_convertida = convert_quantity(quantidade, unidade_uso, insumo_unidade)
    return quantidade_convertida * insumo_custo_unitario
