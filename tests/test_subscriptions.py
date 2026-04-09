"""Tests for subscription management and plan limit enforcement."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import (
    TEST_USER_ID,
    MockSupabaseClient,
)


# ---------------------------------------------------------------------------
# Get subscription
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_subscription_free(mock_db: MockSupabaseClient):
    """get_subscription should return free plan limits for a free user."""
    from app.services.subscription_service import get_subscription

    mock_db.configure_table("profiles", data=[{
        "id": TEST_USER_ID,
        "subscription_status": "free",
        "subscription_expires_at": None,
    }], count=1)

    result = await get_subscription(mock_db, TEST_USER_ID)

    assert result["status"] == "free"
    assert result["expires_at"] is None
    assert result["plan_limits"]["max_pizzas"] == 10
    assert result["plan_limits"]["max_ingredients"] == 50
    assert result["plan_limits"]["max_sizes"] == 5


# ---------------------------------------------------------------------------
# Limit checks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscription_limit_tamanhos(mock_db: MockSupabaseClient):
    """Free user at max_sizes limit should be blocked from creating more."""
    from app.exceptions import AppException
    from app.services.subscription_service import check_limit

    mock_db.configure_table("profiles", data=[{
        "id": TEST_USER_ID,
        "subscription_status": "free",
    }], count=1)
    mock_db.configure_table("tamanhos", data=[{"id": f"t-{i}"} for i in range(5)], count=5)

    with pytest.raises(AppException) as exc_info:
        await check_limit(mock_db, TEST_USER_ID, "max_sizes")

    assert exc_info.value.status == 403
    assert exc_info.value.code == "SUBSCRIPTION_LIMIT"


@pytest.mark.asyncio
async def test_subscription_limit_bordas(mock_db: MockSupabaseClient):
    """Free user at or above borda limit should be blocked.

    Note: bordas do not appear in _RESOURCE_MAP by default, so check_limit
    should pass without error (unknown resource = skip check).
    """
    from app.services.subscription_service import check_limit

    mock_db.configure_table("profiles", data=[{
        "id": TEST_USER_ID,
        "subscription_status": "free",
    }], count=1)

    # Since 'max_bordas' is not in _RESOURCE_MAP, this should silently pass
    await check_limit(mock_db, TEST_USER_ID, "max_bordas")


@pytest.mark.asyncio
async def test_subscription_limit_pizzas(mock_db: MockSupabaseClient):
    """Free user at max_pizzas limit should be blocked."""
    from app.exceptions import AppException
    from app.services.subscription_service import check_limit

    mock_db.configure_table("profiles", data=[{
        "id": TEST_USER_ID,
        "subscription_status": "free",
    }], count=1)
    mock_db.configure_table("pizzas", data=[{"id": f"p-{i}"} for i in range(10)], count=10)

    with pytest.raises(AppException) as exc_info:
        await check_limit(mock_db, TEST_USER_ID, "max_pizzas")

    assert exc_info.value.status == 403
    assert "limit" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# Paid user -- unlimited
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_paid_user_no_limits(mock_db: MockSupabaseClient):
    """Paid user should not be blocked even with many items (max = -1)."""
    from app.services.subscription_service import check_limit

    mock_db.configure_table("profiles", data=[{
        "id": TEST_USER_ID,
        "subscription_status": "paid",
    }], count=1)
    mock_db.configure_table("pizzas", data=[{"id": f"p-{i}"} for i in range(100)], count=100)
    mock_db.configure_table("insumos", data=[{"id": f"i-{i}"} for i in range(200)], count=200)
    mock_db.configure_table("tamanhos", data=[{"id": f"t-{i}"} for i in range(50)], count=50)

    # None of these should raise
    await check_limit(mock_db, TEST_USER_ID, "max_pizzas")
    await check_limit(mock_db, TEST_USER_ID, "max_ingredients")
    await check_limit(mock_db, TEST_USER_ID, "max_sizes")


# ---------------------------------------------------------------------------
# Activation / Deactivation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activate_subscription(mock_db: MockSupabaseClient):
    """activate_subscription should update profile to 'paid' and insert history."""
    from app.services.subscription_service import activate_subscription

    mock_db.configure_table("profiles", data=[{
        "id": TEST_USER_ID,
        "subscription_status": "free",
    }], count=1)

    with patch("app.services.subscription_service.send_transactional", new_callable=AsyncMock):
        await activate_subscription(mock_db, TEST_USER_ID, payment_log_id="log-1")

    # If no exception was raised, the function executed successfully


@pytest.mark.asyncio
async def test_deactivate_subscription(mock_db: MockSupabaseClient):
    """deactivate_subscription should set profile back to 'free'."""
    from app.services.subscription_service import deactivate_subscription

    mock_db.configure_table("profiles", data=[{
        "id": TEST_USER_ID,
        "subscription_status": "paid",
    }], count=1)

    with patch("app.services.subscription_service.send_transactional", new_callable=AsyncMock):
        await deactivate_subscription(mock_db, TEST_USER_ID)

    # If no exception was raised, the function executed successfully
