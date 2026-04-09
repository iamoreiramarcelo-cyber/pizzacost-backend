"""Tests for admin service endpoints and authorization."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import (
    NOW_ISO,
    TEST_ADMIN_ID,
    TEST_USER_ID,
    MockSupabaseClient,
)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_dashboard(mock_db: MockSupabaseClient):
    """get_dashboard should return aggregate stats."""
    from app.services.admin_service import get_dashboard

    mock_db.configure_table("profiles", data=[
        {"id": "u1", "subscription_status": "free"},
        {"id": "u2", "subscription_status": "paid"},
        {"id": "u3", "subscription_status": "paid"},
    ], count=3)
    mock_db.configure_table("subscription_history", data=[], count=0)

    result = await get_dashboard(mock_db)

    assert "total_users" in result
    assert "paid_users" in result
    assert "free_users" in result
    assert "mrr" in result
    assert "new_signups_30d" in result
    assert "churn_rate" in result
    assert isinstance(result["mrr"], float)


# ---------------------------------------------------------------------------
# List users
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_list_users(mock_db: MockSupabaseClient):
    """list_users should return paginated user profiles."""
    from app.services.admin_service import list_users

    mock_db.configure_table("profiles", data=[
        {"id": "u1", "email": "a@test.com", "subscription_status": "free", "created_at": NOW_ISO},
        {"id": "u2", "email": "b@test.com", "subscription_status": "paid", "created_at": NOW_ISO},
    ], count=2)

    users, total = await list_users(mock_db, page=1, per_page=20)

    assert total == 2
    assert len(users) == 2


# ---------------------------------------------------------------------------
# Create user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_create_user(mock_db: MockSupabaseClient):
    """Admin should be able to create a user via create_user service."""
    from app.services.admin_service import create_user

    data = {
        "email": "newuser@test.com",
        "password": "StrongPass123!",
        "nome_loja": "Nova Pizzaria",
        "telefone": "+5511988887777",
        "role": "user",
    }

    profile = await create_user(mock_db, data)

    assert profile is not None
    assert "email" in profile or "id" in profile


# ---------------------------------------------------------------------------
# Update user subscription
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_update_subscription(mock_db: MockSupabaseClient):
    """Admin can update a user's subscription_status."""
    from app.services.admin_service import update_user

    mock_db.configure_table("profiles", data=[{
        "id": TEST_USER_ID,
        "email": "user@test.com",
        "subscription_status": "free",
    }], count=1)

    result = await update_user(
        mock_db,
        TEST_USER_ID,
        {"subscription_status": "paid"},
    )

    assert result["subscription_status"] == "paid"


# ---------------------------------------------------------------------------
# Non-admin forbidden
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_admin_forbidden():
    """Regular user calling require_admin should get 403."""
    from app.exceptions import AppException
    from app.middleware.auth import UserContext, require_admin

    regular_user = UserContext(id=TEST_USER_ID, email="user@test.com", role="user")

    with pytest.raises(AppException) as exc_info:
        require_admin(user=regular_user)

    assert exc_info.value.status == 403
    assert "admin" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_admin_role_accepted():
    """Admin user should pass require_admin without error."""
    from app.middleware.auth import UserContext, require_admin

    admin_user = UserContext(id=TEST_ADMIN_ID, email="admin@test.com", role="admin")

    result = require_admin(user=admin_user)
    assert result.role == "admin"


@pytest.mark.asyncio
async def test_super_admin_role_accepted():
    """Super admin should also pass require_admin."""
    from app.middleware.auth import UserContext, require_admin

    super_admin = UserContext(id=TEST_ADMIN_ID, email="super@test.com", role="super_admin")

    result = require_admin(user=super_admin)
    assert result.role == "super_admin"
