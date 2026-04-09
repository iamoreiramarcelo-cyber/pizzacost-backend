"""Payment webhook processing service for PizzaCost Pro (MercadoPago)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

from supabase import Client

from app.exceptions import AppException

logger = logging.getLogger(__name__)

# MercadoPago status mapping
_STATUS_MAP: dict[str, str] = {
    "approved": "approved",
    "authorized": "approved",
    "in_process": "pending",
    "pending": "pending",
    "rejected": "rejected",
    "cancelled": "rejected",
    "refunded": "refunded",
    "charged_back": "refunded",
}


# ---------------------------------------------------------------------------
# Signature validation
# ---------------------------------------------------------------------------

def _validate_signature(payload_bytes: bytes, signature: str, webhook_secret: str) -> None:
    """Validate HMAC-SHA256 signature from MercadoPago webhook.

    Raises:
        AppException: If signature is missing or does not match.
    """
    if not signature or not webhook_secret:
        raise AppException(
            code="INVALID_SIGNATURE",
            message="Missing webhook signature.",
            status=401,
        )

    expected = hmac.new(
        key=webhook_secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # The signature header may have format "sha256=<hex>"
    received = signature.replace("sha256=", "").strip()

    if not hmac.compare_digest(expected, received):
        raise AppException(
            code="INVALID_SIGNATURE",
            message="Webhook signature verification failed.",
            status=401,
        )


# ---------------------------------------------------------------------------
# Main webhook handler
# ---------------------------------------------------------------------------

async def process_webhook(
    db: Client,
    payload: dict,
    signature: str,
    webhook_secret: str,
    raw_body: bytes | None = None,
) -> None:
    """Process an incoming MercadoPago payment webhook.

    Steps:
        1. Validate the HMAC signature against the raw request body.
        2. Check idempotency (skip if same payment + status already processed).
        3. Parse payment status.
        4. Insert ``payment_logs`` record.
        5. Activate or deactivate subscription based on status.

    Args:
        raw_body: The original raw HTTP request body bytes. Must be provided
                  for correct HMAC validation. Falls back to re-serializing
                  the payload dict if not provided (less reliable).
    """
    # 1. Validate signature against raw body (not re-serialized JSON)
    if raw_body is not None:
        payload_bytes = raw_body
    else:
        logger.warning("process_webhook called without raw_body -- HMAC may fail")
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    _validate_signature(payload_bytes, signature, webhook_secret)

    # 2. Extract payment info
    data = payload.get("data", {})
    external_payment_id = str(data.get("id", payload.get("id", "")))
    action = payload.get("action", "")
    raw_status = data.get("status", action)

    if not external_payment_id:
        logger.warning("Webhook received without payment ID: %s", payload)
        raise AppException(
            code="INVALID_PAYLOAD",
            message="Missing payment ID in webhook payload.",
            status=400,
        )

    # 3. Parse status (before idempotency check so we can compare)
    status = _STATUS_MAP.get(raw_status, "unknown")

    # 4. Idempotency check -- skip only if same payment AND same status already logged
    existing = (
        db.table("payment_logs")
        .select("id, status")
        .eq("external_payment_id", external_payment_id)
        .order("created_at", desc=True)
        .execute()
    )
    if existing.data:
        last_status = existing.data[0].get("status")
        if last_status == status:
            logger.info("Duplicate webhook for payment %s status %s -- skipping", external_payment_id, status)
            return
        logger.info("Payment %s status changed: %s -> %s", external_payment_id, last_status, status)

    # Extract user identification from payload metadata
    metadata = data.get("metadata") or {}
    user_id = metadata.get("user_id")
    amount = data.get("transaction_amount") or data.get("amount")

    if not user_id:
        logger.error("Webhook missing user_id in metadata: %s", external_payment_id)
        raise AppException(
            code="INVALID_PAYLOAD",
            message="Missing user_id in payment metadata.",
            status=400,
        )

    now = datetime.now(timezone.utc).isoformat()

    # 5. Insert payment log
    payment_log = {
        "user_id": user_id,
        "external_payment_id": external_payment_id,
        "provider": "mercadopago",
        "status": status,
        "amount": float(amount) if amount else 0.0,
        "raw_payload": payload,
        "created_at": now,
    }
    log_result = db.table("payment_logs").insert(payment_log).execute()
    payment_log_id = log_result.data[0]["id"] if log_result.data else None

    # 6. Subscription actions
    from app.services.subscription_service import activate_subscription, deactivate_subscription

    if status == "approved":
        logger.info("Payment approved for user %s -- activating subscription", user_id)
        await activate_subscription(
            db,
            user_id=user_id,
            payment_log_id=str(payment_log_id) if payment_log_id else None,
            changed_by="mercadopago_webhook",
            reason=f"Payment {external_payment_id} approved",
        )
    elif status in ("rejected", "refunded"):
        logger.info("Payment %s for user %s -- deactivating subscription", status, user_id)
        await deactivate_subscription(
            db,
            user_id=user_id,
            reason=f"Payment {external_payment_id} {status}",
        )
    else:
        logger.info("Payment %s status '%s' -- no subscription change", external_payment_id, status)
