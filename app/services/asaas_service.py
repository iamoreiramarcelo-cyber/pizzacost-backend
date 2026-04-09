import httpx
import logging
from datetime import date, timedelta
from app.config import get_settings
from app.exceptions import AppException

logger = logging.getLogger("pizzacost.asaas")


def _base_url() -> str:
    """Return Asaas base URL based on environment."""
    settings = get_settings()
    if settings.is_production:
        return "https://api.asaas.com"
    return "https://api-sandbox.asaas.com"


def _headers():
    settings = get_settings()
    return {
        "access_token": settings.ASAAS_API_KEY,
        "Content-Type": "application/json",
    }


def create_customer(name: str, email: str, cpf_cnpj: str, phone: str = None) -> dict:
    """Create a customer in Asaas."""
    with httpx.Client(base_url=_base_url(), headers=_headers(), timeout=30) as client:
        payload = {
            "name": name,
            "email": email,
            "cpfCnpj": cpf_cnpj.replace(".", "").replace("-", "").replace("/", ""),
        }
        if phone:
            payload["mobilePhone"] = phone.replace("(", "").replace(")", "").replace("-", "").replace(" ", "")

        response = client.post("/v3/customers", json=payload)
        if response.status_code != 200:
            logger.error(f"Asaas create_customer error: {response.text}")
            errors = response.json().get("errors", [{}])
            raise AppException("PAYMENT_ERROR", f"Erro ao criar cliente: {errors[0].get('description', 'Erro desconhecido')}", 400)
        return response.json()


def find_customer_by_email(email: str) -> dict | None:
    """Find an existing customer by email."""
    with httpx.Client(base_url=_base_url(), headers=_headers(), timeout=30) as client:
        response = client.get("/v3/customers", params={"email": email})
        if response.status_code == 200:
            data = response.json()
            if data.get("data") and len(data["data"]) > 0:
                return data["data"][0]
    return None


def find_customer_subscriptions(customer_id: str) -> list:
    """Find all subscriptions for a customer."""
    with httpx.Client(base_url=_base_url(), headers=_headers(), timeout=30) as client:
        response = client.get(f"/v3/subscriptions", params={"customer": customer_id})
        if response.status_code == 200:
            return response.json().get("data", [])
        return []


def create_subscription(
    customer_id: str,
    value: float,
    billing_type: str = "UNDEFINED",
    cycle: str = "MONTHLY",
    description: str = "PizzaCost Pro - Plano Pro",
    next_due_date: str = None,
    external_reference: str = None,
) -> dict:
    """Create a subscription in Asaas."""
    if not next_due_date:
        next_due_date = (date.today() + timedelta(days=1)).isoformat()

    with httpx.Client(base_url=_base_url(), headers=_headers(), timeout=30) as client:
        payload = {
            "customer": customer_id,
            "billingType": billing_type,
            "value": value,
            "nextDueDate": next_due_date,
            "cycle": cycle,
            "description": description,
        }
        if external_reference:
            payload["externalReference"] = external_reference

        response = client.post("/v3/subscriptions", json=payload)
        if response.status_code != 200:
            logger.error(f"Asaas create_subscription error: {response.text}")
            errors = response.json().get("errors", [{}])
            raise AppException("PAYMENT_ERROR", f"Erro ao criar assinatura: {errors[0].get('description', 'Erro desconhecido')}", 400)
        return response.json()


def get_subscription(subscription_id: str) -> dict:
    """Get subscription details."""
    with httpx.Client(base_url=_base_url(), headers=_headers(), timeout=30) as client:
        response = client.get(f"/v3/subscriptions/{subscription_id}")
        if response.status_code != 200:
            raise AppException("NOT_FOUND", "Assinatura nao encontrada.", 404)
        return response.json()


def cancel_subscription(subscription_id: str) -> dict:
    """Cancel a subscription."""
    with httpx.Client(base_url=_base_url(), headers=_headers(), timeout=30) as client:
        response = client.delete(f"/v3/subscriptions/{subscription_id}")
        if response.status_code != 200:
            raise AppException("PAYMENT_ERROR", "Erro ao cancelar assinatura.", 400)
        return response.json()


def get_subscription_payments(subscription_id: str) -> list:
    """Get all payments for a subscription."""
    with httpx.Client(base_url=_base_url(), headers=_headers(), timeout=30) as client:
        response = client.get(f"/v3/subscriptions/{subscription_id}/payments")
        if response.status_code == 200:
            return response.json().get("data", [])
        logger.warning(f"Failed to get payments for subscription {subscription_id}: {response.status_code} {response.text}")
        return []


def get_payment_pix_qrcode(payment_id: str) -> dict:
    """Get PIX QR code for a payment."""
    with httpx.Client(base_url=_base_url(), headers=_headers(), timeout=30) as client:
        response = client.get(f"/v3/payments/{payment_id}/pixQrCode")
        if response.status_code == 200:
            return response.json()
        return {}


def get_payment_boleto(payment_id: str) -> dict:
    """Get boleto identification field."""
    with httpx.Client(base_url=_base_url(), headers=_headers(), timeout=30) as client:
        response = client.get(f"/v3/payments/{payment_id}/identificationField")
        if response.status_code == 200:
            return response.json()
        return {}


def get_payment_status(payment_id: str) -> dict:
    """Get payment status."""
    with httpx.Client(base_url=_base_url(), headers=_headers(), timeout=30) as client:
        response = client.get(f"/v3/payments/{payment_id}/status")
        if response.status_code == 200:
            return response.json()
        return {}


# --- Webhook processing ---

PAYMENT_CONFIRMED_EVENTS = ["PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"]


def process_webhook(db, payload: dict, webhook_token: str = None) -> dict:
    """Process an Asaas webhook event."""
    event = payload.get("event")
    payment_data = payload.get("payment", {})

    if not event or not payment_data:
        logger.warning(f"Webhook ignored: missing event or payment data. Payload keys: {list(payload.keys())}")
        return {"status": "ignored", "reason": "invalid payload"}

    payment_id = payment_data.get("id")
    subscription_id = payment_data.get("subscription")
    customer_id = payment_data.get("customer")
    external_ref = payment_data.get("externalReference")
    status = payment_data.get("status")
    value = payment_data.get("value", 0)
    billing_type = payment_data.get("billingType")
    invoice_url = payment_data.get("invoiceUrl")

    logger.info(
        f"Webhook processing: event={event}, payment_id={payment_id}, "
        f"subscription_id={subscription_id}, customer_id={customer_id}, "
        f"external_ref={external_ref}, status={status}"
    )

    # Log payment
    try:
        db.table("payment_logs").insert({
            "user_id": external_ref,
            "external_payment_id": payment_id,
            "provider": "asaas",
            "status": _map_status(status),
            "amount_brl": value,
            "payment_method": billing_type.lower() if billing_type else None,
            "asaas_payment_id": payment_id,
            "billing_type": billing_type,
            "invoice_url": invoice_url,
            "webhook_payload": payload,
        }).execute()
    except Exception as e:
        logger.error(f"Failed to log payment to payment_logs: {e}")

    # --- FIX (C): More robust activation with fallback to customer lookup ---
    if event in PAYMENT_CONFIRMED_EVENTS:
        user_id = external_ref

        # If external_ref is missing, try to find user by customer_id or subscription_id
        if not user_id and (customer_id or subscription_id):
            logger.warning(f"Webhook has no externalReference, trying to find user by customer_id={customer_id} or subscription_id={subscription_id}")
            try:
                if subscription_id:
                    lookup = db.table("profiles").select("id").eq("asaas_subscription_id", subscription_id).single().execute()
                    if lookup.data:
                        user_id = lookup.data["id"]
                if not user_id and customer_id:
                    lookup = db.table("profiles").select("id").eq("asaas_customer_id", customer_id).single().execute()
                    if lookup.data:
                        user_id = lookup.data["id"]
            except Exception as e:
                logger.error(f"Failed to lookup user by customer/subscription: {e}")

        if not user_id:
            logger.error(f"Cannot activate subscription: no user found for payment {payment_id} (external_ref={external_ref}, customer={customer_id}, subscription={subscription_id})")
            return {"status": "error", "reason": "user_not_found"}

        try:
            # Get current status before updating
            current_profile = db.table("profiles").select("subscription_status").eq("id", user_id).single().execute()
            old_status = current_profile.data.get("subscription_status", "free") if current_profile.data else "free"

            update_data = {"subscription_status": "paid"}
            if customer_id:
                update_data["asaas_customer_id"] = customer_id
            if subscription_id:
                update_data["asaas_subscription_id"] = subscription_id

            result = db.table("profiles").update(update_data).eq("id", user_id).execute()
            logger.info(f"Profile updated to 'paid' for user {user_id}: {result.data}")

            try:
                db.table("subscription_history").insert({
                    "user_id": user_id,
                    "old_status": old_status,
                    "new_status": "paid",
                    "reason": f"asaas_webhook_{event}",
                    "changed_by": "system",
                }).execute()
            except Exception as e:
                logger.warning(f"Failed to log subscription history: {e}")

            logger.info(f"Subscription activated for user {user_id} via webhook event {event}")
            return {"status": "processed", "action": "activated"}
        except Exception as e:
            logger.error(f"Activation failed for user {user_id}: {e}", exc_info=True)
            return {"status": "error", "reason": str(e)}

    if event == "PAYMENT_REFUNDED" and external_ref:
        try:
            db.table("profiles").update({"subscription_status": "free"}).eq("id", external_ref).execute()
            db.table("subscription_history").insert({
                "user_id": external_ref,
                "old_status": "paid",
                "new_status": "free",
                "reason": "asaas_REFUNDED",
                "changed_by": "system",
            }).execute()
            return {"status": "processed", "action": "deactivated"}
        except Exception as e:
            logger.error(f"Deactivation failed for user {external_ref}: {e}")
            return {"status": "error", "reason": str(e)}

    return {"status": "processed", "action": "logged"}


def sandbox_confirm_payment(payment_id: str) -> dict:
    """(Sandbox only) Confirm a payment for testing."""
    with httpx.Client(base_url=_base_url(), headers=_headers(), timeout=30) as client:
        response = client.post(f"/v3/sandbox/payment/{payment_id}/confirm")
        if response.status_code == 200:
            return response.json()
        logger.error(f"Sandbox confirm failed: {response.text}")
        return {}


def _map_status(asaas_status: str) -> str:
    mapping = {
        "PENDING": "pending",
        "CONFIRMED": "approved",
        "RECEIVED": "approved",
        "OVERDUE": "pending",
        "REFUNDED": "refunded",
        "REFUND_REQUESTED": "refunded",
        "CHARGEBACK_REQUESTED": "rejected",
        "CHARGEBACK_DISPUTE": "rejected",
    }
    return mapping.get(asaas_status, "pending")
