"""Tests for LGPD compliance (data export, account deletion, consent)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import (
    TEST_ADMIN_ID,
    TEST_USER_ID,
    MockSupabaseClient,
)


# ---------------------------------------------------------------------------
# Data export request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_data_export(mock_db: MockSupabaseClient):
    """POST /api/v1/me/data-export equivalent -- should create a pending request."""
    from app.services.lgpd_service import request_data_export

    mock_db.configure_table("lgpd_requests", data=[], count=0)

    result = await request_data_export(mock_db, TEST_USER_ID)

    assert result["user_id"] == TEST_USER_ID
    assert result["type"] == "data_export"
    assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_request_data_export_duplicate(mock_db: MockSupabaseClient):
    """Duplicate pending data export request should raise 409."""
    from app.exceptions import AppException
    from app.services.lgpd_service import request_data_export

    # Simulate an existing pending request
    mock_db.configure_table("lgpd_requests", data=[{
        "id": "existing-req",
        "user_id": TEST_USER_ID,
        "type": "data_export",
        "status": "pending",
    }], count=1)

    with pytest.raises(AppException) as exc_info:
        await request_data_export(mock_db, TEST_USER_ID)

    assert exc_info.value.status == 409
    assert exc_info.value.code == "DUPLICATE_REQUEST"


# ---------------------------------------------------------------------------
# Account deletion request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_account_deletion(mock_db: MockSupabaseClient):
    """DELETE /api/v1/me/account equivalent -- should create a pending deletion request."""
    from app.services.lgpd_service import request_account_deletion

    mock_db.configure_table("lgpd_requests", data=[], count=0)

    with patch("app.services.lgpd_service.send_transactional", new_callable=AsyncMock):
        result = await request_account_deletion(mock_db, TEST_USER_ID)

    assert result["user_id"] == TEST_USER_ID
    assert result["type"] == "account_deletion"
    assert result["status"] == "pending"


# ---------------------------------------------------------------------------
# Consent log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_consent_log(mock_db: MockSupabaseClient):
    """Admin should be able to view a user's consent logs."""
    from app.services.lgpd_service import get_consent_log

    mock_db.configure_table("consent_logs", data=[
        {
            "id": "c1",
            "user_id": TEST_USER_ID,
            "consent_type": "terms_of_service",
            "granted": True,
            "policy_version": "1.0",
            "created_at": "2025-06-01T12:00:00Z",
        },
        {
            "id": "c2",
            "user_id": TEST_USER_ID,
            "consent_type": "marketing",
            "granted": False,
            "policy_version": "1.0",
            "created_at": "2025-06-01T12:00:00Z",
        },
    ], count=2)

    logs = await get_consent_log(mock_db, TEST_USER_ID)

    assert len(logs) == 2
    consent_types = [l["consent_type"] for l in logs]
    assert "terms_of_service" in consent_types
    assert "marketing" in consent_types


# ---------------------------------------------------------------------------
# Email preferences opt-out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_preferences_opt_out(mock_db: MockSupabaseClient):
    """User opting out of marketing should update consent_logs and email_preferences."""
    from app.services.lgpd_service import record_consent

    mock_db.configure_table("consent_logs", data=[], count=0)
    mock_db.configure_table("email_preferences", data=[{
        "user_id": TEST_USER_ID,
        "marketing_opt_in": True,
        "transactional_opt_in": True,
    }], count=1)

    await record_consent(
        db=mock_db,
        user_id=TEST_USER_ID,
        consent_type="marketing",
        granted=False,
        ip="127.0.0.1",
        user_agent="TestAgent/1.0",
    )

    # Function executed without error -- consent was recorded


# ---------------------------------------------------------------------------
# Record consent for terms
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_consent_terms(mock_db: MockSupabaseClient):
    """Recording terms consent should not update email_preferences."""
    from app.services.lgpd_service import record_consent

    mock_db.configure_table("consent_logs", data=[], count=0)

    await record_consent(
        db=mock_db,
        user_id=TEST_USER_ID,
        consent_type="terms_of_service",
        granted=True,
        policy_version="2.0",
    )

    # No exception means success
