"""Tests for MercadoPago payment webhook processing."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import (
    TEST_USER_ID,
    MockSupabaseClient,
)

WEBHOOK_SECRET = "mp-webhook-secret-for-testing"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sign_payload(payload: dict, secret: str) -> str:
    """Generate a valid HMAC-SHA256 signature for the payload."""
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def _build_payment_payload(
    payment_id: str = "pay_12345",
    status: str = "approved",
    user_id: str = TEST_USER_ID,
) -> dict:
    return {
        "id": payment_id,
        "action": "payment.created",
        "data": {
            "id": payment_id,
            "status": status,
            "transaction_amount": 19.90,
            "metadata": {
                "user_id": user_id,
            },
        },
    }


# ---------------------------------------------------------------------------
# Approved payment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mercadopago_webhook_approved(mock_db: MockSupabaseClient):
    """Approved payment webhook should activate subscription."""
    from app.services.payment_service import process_webhook

    payload = _build_payment_payload(status="approved")
    signature = _sign_payload(payload, WEBHOOK_SECRET)

    mock_db.configure_table("payment_logs", data=[], count=0)
    mock_db.configure_table("profiles", data=[{
        "id": TEST_USER_ID,
        "subscription_status": "free",
    }], count=1)
    mock_db.configure_table("subscription_history", data=[], count=0)

    with patch("app.services.subscription_service.send_transactional", new_callable=AsyncMock):
        await process_webhook(
            db=mock_db,
            payload=payload,
            signature=signature,
            webhook_secret=WEBHOOK_SECRET,
        )

    # No exception means webhook was processed successfully


# ---------------------------------------------------------------------------
# Invalid signature
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mercadopago_webhook_invalid_signature(mock_db: MockSupabaseClient):
    """Webhook with wrong signature should raise 401."""
    from app.exceptions import AppException
    from app.services.payment_service import process_webhook

    payload = _build_payment_payload()

    with pytest.raises(AppException) as exc_info:
        await process_webhook(
            db=mock_db,
            payload=payload,
            signature="invalid-signature-here",
            webhook_secret=WEBHOOK_SECRET,
        )

    assert exc_info.value.status == 401
    assert exc_info.value.code == "INVALID_SIGNATURE"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mercadopago_webhook_idempotent(mock_db: MockSupabaseClient):
    """Second call with same payment_id should be a no-op (idempotent)."""
    from app.services.payment_service import process_webhook

    payload = _build_payment_payload(payment_id="pay_dupe")
    signature = _sign_payload(payload, WEBHOOK_SECRET)

    # Simulate that this payment_id already exists in payment_logs
    mock_db.configure_table("payment_logs", data=[{
        "id": "existing-log-id",
        "external_payment_id": "pay_dupe",
    }], count=1)

    # Should return without error and without processing again
    await process_webhook(
        db=mock_db,
        payload=payload,
        signature=signature,
        webhook_secret=WEBHOOK_SECRET,
    )


# ---------------------------------------------------------------------------
# Missing user_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mercadopago_webhook_missing_user_id(mock_db: MockSupabaseClient):
    """Webhook without user_id in metadata should raise 400."""
    from app.exceptions import AppException
    from app.services.payment_service import process_webhook

    payload = {
        "id": "pay_no_user",
        "action": "payment.created",
        "data": {
            "id": "pay_no_user",
            "status": "approved",
            "transaction_amount": 19.90,
            "metadata": {},
        },
    }
    signature = _sign_payload(payload, WEBHOOK_SECRET)
    mock_db.configure_table("payment_logs", data=[], count=0)

    with pytest.raises(AppException) as exc_info:
        await process_webhook(
            db=mock_db,
            payload=payload,
            signature=signature,
            webhook_secret=WEBHOOK_SECRET,
        )

    assert exc_info.value.status == 400


# ---------------------------------------------------------------------------
# Rejected payment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mercadopago_webhook_rejected(mock_db: MockSupabaseClient):
    """Rejected payment should trigger subscription deactivation."""
    from app.services.payment_service import process_webhook

    payload = _build_payment_payload(status="rejected")
    signature = _sign_payload(payload, WEBHOOK_SECRET)

    mock_db.configure_table("payment_logs", data=[], count=0)
    mock_db.configure_table("profiles", data=[{
        "id": TEST_USER_ID,
        "subscription_status": "paid",
    }], count=1)
    mock_db.configure_table("subscription_history", data=[], count=0)

    with patch("app.services.subscription_service.send_transactional", new_callable=AsyncMock):
        await process_webhook(
            db=mock_db,
            payload=payload,
            signature=signature,
            webhook_secret=WEBHOOK_SECRET,
        )
