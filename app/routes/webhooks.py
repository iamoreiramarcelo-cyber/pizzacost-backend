"""Webhook routes for PizzaCost Pro (MercadoPago, Resend)."""

import logging

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.config import get_settings
from app.database import get_supabase_client
from app.services import payment_service, email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])


@router.post("/mercadopago")
async def mercadopago_webhook(
    request: Request,
    db: Client = Depends(get_supabase_client),
):
    """Process incoming MercadoPago payment webhook.

    No authentication required. Validates HMAC signature from the request headers.
    """
    settings = get_settings()

    raw_body = await request.body()
    payload = await request.json()
    signature = request.headers.get("x-signature", "") or request.headers.get("x-hub-signature-256", "")

    await payment_service.process_webhook(
        db=db,
        payload=payload,
        signature=signature,
        webhook_secret=settings.MERCADOPAGO_WEBHOOK_SECRET,
        raw_body=raw_body,
    )

    return {"status": "ok"}


@router.post("/resend")
async def resend_webhook(
    request: Request,
    db: Client = Depends(get_supabase_client),
):
    """Process incoming Resend email webhook (delivery, open, click tracking).

    Resend sends webhook events for email status updates.
    TODO: Validate Resend webhook signature (svix-id, svix-timestamp,
    svix-signature headers) using the Svix library for production security.
    """
    # Basic validation: Resend webhooks include these headers
    svix_id = request.headers.get("svix-id")
    if not svix_id:
        logger.warning("Resend webhook missing svix-id header -- possible forgery")
        return {"status": "ignored", "reason": "missing signature headers"}

    payload = await request.json()

    event_type = payload.get("type", "")
    data = payload.get("data", {})

    resend_message_id = data.get("email_id") or data.get("message_id")

    if not resend_message_id:
        logger.warning("Resend webhook received without message ID: %s", payload)
        return {"status": "ignored", "reason": "no message id"}

    # Map Resend event types to status
    status_map = {
        "email.sent": "sent",
        "email.delivered": "delivered",
        "email.delivery_delayed": "delayed",
        "email.complained": "complained",
        "email.bounced": "bounced",
        "email.opened": "opened",
        "email.clicked": "clicked",
    }

    status = status_map.get(event_type)
    if not status:
        logger.info("Resend webhook unhandled event type: %s", event_type)
        return {"status": "ignored", "reason": f"unhandled event type: {event_type}"}

    opened_at = data.get("created_at") if event_type == "email.opened" else None
    clicked_at = data.get("created_at") if event_type == "email.clicked" else None

    await email_service.update_email_status(
        db=db,
        resend_message_id=resend_message_id,
        status=status,
        opened_at=opened_at,
        clicked_at=clicked_at,
    )

    return {"status": "ok"}
