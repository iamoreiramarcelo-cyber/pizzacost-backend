"""Asaas payment integration routes for PizzaCost Pro."""

from fastapi import APIRouter, Depends, Request
from app.middleware.auth import get_current_user, require_admin, UserContext
from app.database import get_supabase_client
from app.services import asaas_service
from app.middleware.audit import audit_log
from app.exceptions import AppException
from supabase import Client
from pydantic import BaseModel
import logging

logger = logging.getLogger("pizzacost.asaas")

router = APIRouter(prefix="/api/v1/asaas", tags=["Asaas Payments"])


class CreateSubscriptionRequest(BaseModel):
    cpf_cnpj: str  # Required by Asaas
    billing_type: str = "UNDEFINED"  # UNDEFINED, PIX, BOLETO, CREDIT_CARD
    cycle: str = "MONTHLY"  # MONTHLY or YEARLY
    nome: str | None = None  # Override name if needed


class CancelSubscriptionRequest(BaseModel):
    reason: str | None = None


@router.post("/subscribe")
async def subscribe(
    data: CreateSubscriptionRequest,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Create a NEW Asaas subscription for the current user.
    NEVER activates subscription here — activation only via webhook or admin."""
    profile = db.table("profiles").select("*").eq("id", user.id).single().execute()
    if not profile.data:
        raise AppException("NOT_FOUND", "Perfil nao encontrado.", 404)

    profile_data = profile.data

    if profile_data.get("subscription_status") == "paid":
        raise AppException("CONFLICT", "Voce ja possui uma assinatura ativa.", 409)

    # Cancel any old subscription in Asaas before creating new
    old_sub_id = profile_data.get("asaas_subscription_id")
    if old_sub_id:
        try:
            asaas_service.cancel_subscription(old_sub_id)
            logger.info(f"Cancelled old subscription {old_sub_id} for user {user.id}")
        except Exception:
            pass
        db.table("profiles").update({"asaas_subscription_id": None}).eq("id", user.id).execute()

    # Find or create Asaas customer (always use the CPF provided)
    customer = asaas_service.find_customer_by_email(user.email)
    if customer:
        asaas_customer_id = customer["id"]
    else:
        customer = asaas_service.create_customer(
            name=data.nome or profile_data.get("nome_loja") or user.email.split("@")[0],
            email=user.email,
            cpf_cnpj=data.cpf_cnpj,
            phone=profile_data.get("telefone"),
        )
        asaas_customer_id = customer["id"]

    db.table("profiles").update({"asaas_customer_id": asaas_customer_id}).eq("id", user.id).execute()

    # Create NEW subscription
    value = 29.90 if data.cycle == "MONTHLY" else 238.80
    cycle = data.cycle if data.cycle in ("MONTHLY", "YEARLY") else "MONTHLY"

    subscription = asaas_service.create_subscription(
        customer_id=asaas_customer_id,
        value=value,
        billing_type=data.billing_type,
        cycle=cycle,
        description=f"PizzaCost Pro - Plano {'Mensal' if cycle == 'MONTHLY' else 'Anual'}",
        external_reference=user.id,
    )

    db.table("profiles").update({"asaas_subscription_id": subscription["id"]}).eq("id", user.id).execute()

    # Tag user as 'aquecido' (entered checkout)
    db.table("profiles").update({"tag": "aquecido"}).eq("id", user.id).execute()

    # Get first payment for QR/boleto — but NEVER activate here
    payments = asaas_service.get_subscription_payments(subscription["id"])
    first_payment = payments[0] if payments else None

    result = {
        "subscription_id": subscription["id"],
        "status": "PENDING",
        "value": value,
        "cycle": cycle,
        "next_due_date": subscription.get("nextDueDate"),
    }

    if first_payment and data.billing_type in ("PIX", "UNDEFINED"):
        try:
            pix_data = asaas_service.get_payment_pix_qrcode(first_payment["id"])
            result["pix_qrcode_image"] = pix_data.get("encodedImage")
            result["pix_payload"] = pix_data.get("payload")
        except Exception:
            pass

    if first_payment and data.billing_type == "BOLETO":
        try:
            boleto_data = asaas_service.get_payment_boleto(first_payment["id"])
            result["boleto_barcode"] = boleto_data.get("identificationField")
        except Exception:
            pass

    if first_payment:
        result["invoice_url"] = first_payment.get("invoiceUrl")
        result["payment_id"] = first_payment.get("id")

    # Flag if already paid
    if first_payment and first_payment.get("status") in ("RECEIVED", "CONFIRMED"):
        result["already_paid"] = True

    await audit_log(db, user.id, "SUBSCRIBE", "subscription", subscription["id"], ip=None)

    return {"data": result}


@router.get("/subscription")
async def get_subscription(
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Get current user's subscription details."""
    profile = db.table("profiles").select("asaas_subscription_id, subscription_status").eq("id", user.id).single().execute()

    if not profile.data or not profile.data.get("asaas_subscription_id"):
        return {"data": {"status": profile.data.get("subscription_status", "free") if profile.data else "free", "subscription": None}}

    sub = None
    payments = None
    current_status = profile.data.get("subscription_status")

    try:
        sub = asaas_service.get_subscription(profile.data["asaas_subscription_id"])
    except Exception as e:
        logger.error(f"Error getting subscription from Asaas: {e}")
        return {"data": {"status": current_status or "free", "subscription": None, "error": "Erro ao consultar assinatura no Asaas."}}

    try:
        payments = asaas_service.get_subscription_payments(profile.data["asaas_subscription_id"])
    except Exception as e:
        logger.error(f"Error getting payments from Asaas: {e}")
        payments = []

    # NOTE: No self-heal here. Activation ONLY via webhook (POST /webhook)
    # or manual admin action. Polling just returns current state.

    return {"data": {
        "status": current_status,
        "subscription": {
            "id": sub.get("id"),
            "asaas_status": sub.get("status"),
            "value": sub.get("value"),
            "cycle": sub.get("cycle"),
            "next_due_date": sub.get("nextDueDate"),
            "billing_type": sub.get("billingType"),
        } if sub else None,
        "recent_payments": [
            {
                "id": p.get("id"),
                "status": p.get("status"),
                "value": p.get("value"),
                "due_date": p.get("dueDate"),
                "invoice_url": p.get("invoiceUrl"),
            }
            for p in (payments[:5] if payments else [])
        ],
    }}


@router.post("/cancel")
async def cancel_subscription_route(
    data: CancelSubscriptionRequest = None,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Cancel the current user's subscription."""
    profile = db.table("profiles").select("asaas_subscription_id, subscription_status").eq("id", user.id).single().execute()

    if not profile.data or not profile.data.get("asaas_subscription_id"):
        raise AppException("NOT_FOUND", "Nenhuma assinatura ativa encontrada.", 404)

    # Cancel in Asaas
    asaas_service.cancel_subscription(profile.data["asaas_subscription_id"])

    # Update profile
    db.table("profiles").update({
        "subscription_status": "free",
        "asaas_subscription_id": None,
        "tag": "nao_assinante",
    }).eq("id", user.id).execute()

    # Log history
    db.table("subscription_history").insert({
        "user_id": user.id,
        "old_status": "paid",
        "new_status": "free",
        "reason": data.reason if data else "user_cancelled",
        "changed_by": user.id,
    }).execute()

    await audit_log(db, user.id, "CANCEL_SUBSCRIPTION", "subscription", profile.data["asaas_subscription_id"], ip=None)

    return {"data": {"status": "cancelled", "message": "Assinatura cancelada com sucesso."}}


@router.get("/payment/{payment_id}/pix")
async def get_pix_qrcode(
    payment_id: str,
    user: UserContext = Depends(get_current_user),
):
    """Get PIX QR code for a specific payment."""
    data = asaas_service.get_payment_pix_qrcode(payment_id)
    return {"data": data}


@router.post("/sandbox/confirm/{payment_id}")
def sandbox_confirm(
    payment_id: str,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """(Sandbox only) Manually confirm a payment for testing."""
    from app.config import get_settings
    settings = get_settings()
    if settings.is_production:
        raise AppException("FORBIDDEN", "Sandbox only endpoint.", 403)
    result = asaas_service.sandbox_confirm_payment(payment_id)
    return {"data": result}


@router.post("/webhook")
async def asaas_webhook(request: Request, db: Client = Depends(get_supabase_client)):
    """Receive Asaas webhook events. No auth required -- Asaas sends these."""
    try:
        payload = await request.json()
    except Exception:
        logger.error("Asaas webhook: invalid JSON body")
        return {"status": "error", "reason": "invalid json"}

    # Optional: validate webhook token from query param or header
    webhook_token = request.query_params.get("token")

    event = payload.get("event")
    payment_data = payload.get("payment", {})
    logger.info(f"Asaas webhook received: event={event}, payment_id={payment_data.get('id')}, status={payment_data.get('status')}, external_ref={payment_data.get('externalReference')}")

    result = asaas_service.process_webhook(db, payload, webhook_token)
    logger.info(f"Asaas webhook result: {result}")
    return result
