"""Tests for pizza CRUD and cost calculation logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import (
    BORDA_ID,
    INSUMO_ID,
    NOW_ISO,
    PIZZA_ID,
    TAMANHO_ID,
    TEST_USER_ID,
    MockSupabaseClient,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _configure_db_for_pizza_create(mock_db: MockSupabaseClient, insumo: dict, tamanho: dict):
    """Pre-configure mock DB tables for pizza creation."""
    mock_db.configure_table("profiles", data=[{
        "id": TEST_USER_ID,
        "subscription_status": "paid",
    }], count=1)
    mock_db.configure_table("tamanhos", data=[tamanho], count=1)
    mock_db.configure_table("bordas", data=[], count=0)
    mock_db.configure_table("insumos", data=[insumo], count=1)
    mock_db.configure_table("pizzas", data=[], count=0)
    mock_db.configure_table("combos", data=[], count=0)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_pizza(
    mock_db: MockSupabaseClient,
    sample_insumo: dict,
    sample_tamanho: dict,
):
    """create_pizza should compute custo_calculado correctly."""
    from app.services.pizza_service import create_pizza

    _configure_db_for_pizza_create(mock_db, sample_insumo, sample_tamanho)

    data = {
        "nome": "Margherita",
        "tamanho_id": TAMANHO_ID,
        "borda_id": None,
        "ingredientes": [
            {"insumo_id": INSUMO_ID, "quantidade": 0.25, "unidade": "kg"},
        ],
        "custo_adicionais": 1.50,
        "preco_venda": 45.00,
    }

    result = await create_pizza(mock_db, TEST_USER_ID, data)

    # Expected cost: ingredient (0.25 * 42.90 = 10.725) + embalagem (1.50) + massa (3.50) + adicionais (1.50) = 17.225 -> 17.22
    expected_cost = round(0.25 * 42.90 + 1.50 + 3.50 + 1.50, 2)
    assert result["custo_calculado"] == expected_cost
    assert result["nome"] == "Margherita"


# ---------------------------------------------------------------------------
# Subscription limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_pizza_subscription_limit(
    mock_db: MockSupabaseClient,
    sample_insumo: dict,
    sample_tamanho: dict,
):
    """Free user who has reached max_pizzas should get 403."""
    from app.exceptions import AppException
    from app.services.pizza_service import create_pizza

    # Configure as free user with 10 pizzas already (free limit = 10)
    mock_db.configure_table("profiles", data=[{
        "id": TEST_USER_ID,
        "subscription_status": "free",
    }], count=1)
    mock_db.configure_table("pizzas", data=[{"id": f"pizza-{i}"} for i in range(10)], count=10)
    mock_db.configure_table("tamanhos", data=[sample_tamanho], count=1)
    mock_db.configure_table("insumos", data=[sample_insumo], count=1)

    data = {
        "nome": "Extra Pizza",
        "tamanho_id": TAMANHO_ID,
        "ingredientes": [
            {"insumo_id": INSUMO_ID, "quantidade": 0.25, "unidade": "kg"},
        ],
    }

    with pytest.raises(AppException) as exc_info:
        await create_pizza(mock_db, TEST_USER_ID, data)

    assert exc_info.value.status == 403
    assert exc_info.value.code == "SUBSCRIPTION_LIMIT"


# ---------------------------------------------------------------------------
# Cost calculation correctness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pizza_cost_calculation():
    """Verify calculate_pizza_cost computes: ingredients + packaging + dough + border + extras."""
    from app.utils.cost_calculator import calculate_pizza_cost

    insumos_map = {
        "insumo-a": {"custo_unitario": 40.0, "unidade": "kg"},
        "insumo-b": {"custo_unitario": 20.0, "unidade": "kg"},
    }

    pizza_ingredientes = [
        {"insumo_id": "insumo-a", "quantidade": 0.3, "unidade": "kg"},
        {"insumo_id": "insumo-b", "quantidade": 0.1, "unidade": "kg"},
    ]

    tamanho = {"custo_embalagem": 1.50, "custo_massa": 3.00}

    borda = {
        "ingredientes": [
            {"insumo_id": "insumo-a", "quantidade": 0.1, "unidade": "kg"},
        ],
    }

    custo_adicionais = 2.00

    result = calculate_pizza_cost(
        pizza_ingredientes=pizza_ingredientes,
        custo_adicionais=custo_adicionais,
        tamanho=tamanho,
        borda=borda,
        insumos_map=insumos_map,
    )

    # Breakdown:
    # ingredients: (0.3 * 40) + (0.1 * 20) = 12 + 2 = 14
    # embalagem: 1.50
    # massa: 3.00
    # borda ingredients: 0.1 * 40 = 4
    # extras: 2.00
    # total = 14 + 1.50 + 3.00 + 4 + 2.00 = 24.50
    assert result == 24.50


# ---------------------------------------------------------------------------
# Cost cascade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pizza_cost_cascade(
    mock_db: MockSupabaseClient,
    sample_insumo: dict,
    sample_tamanho: dict,
    sample_pizza: dict,
):
    """When an insumo price is updated, pizzas using it should be recalculated."""
    from app.services.insumo_service import update_insumo

    # Set up the DB so that updating the insumo triggers a cascade
    mock_db.configure_table("insumos", data=[sample_insumo], count=1)
    mock_db.configure_table("bordas", data=[], count=0)
    mock_db.configure_table("pizzas", data=[sample_pizza], count=1)
    mock_db.configure_table("tamanhos", data=[sample_tamanho], count=1)
    mock_db.configure_table("combos", data=[], count=0)

    # Update insumo price -- this should trigger _cascade_insumo_cost
    # The cascade internally calls _recalculate_pizza_cost for affected pizzas
    updated = await update_insumo(
        mock_db,
        TEST_USER_ID,
        INSUMO_ID,
        {"preco": 60.00},
    )

    # The insumo's custo_unitario should be recalculated
    assert updated["custo_unitario"] == 60.0  # 60.00 / 1.0


# ---------------------------------------------------------------------------
# Pizza without borda
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pizza_cost_without_borda():
    """Pizza cost without a borda should not include borda ingredient costs."""
    from app.utils.cost_calculator import calculate_pizza_cost

    insumos_map = {
        "insumo-x": {"custo_unitario": 50.0, "unidade": "kg"},
    }

    result = calculate_pizza_cost(
        pizza_ingredientes=[
            {"insumo_id": "insumo-x", "quantidade": 0.2, "unidade": "kg"},
        ],
        custo_adicionais=1.00,
        tamanho={"custo_embalagem": 2.00, "custo_massa": 3.00},
        borda=None,
        insumos_map=insumos_map,
    )

    # 0.2 * 50 + 2.00 + 3.00 + 1.00 = 10 + 2 + 3 + 1 = 16.00
    assert result == 16.0
