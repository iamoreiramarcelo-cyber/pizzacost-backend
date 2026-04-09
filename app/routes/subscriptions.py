"""Subscription routes for PizzaCost Pro."""

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.config import get_settings
from app.database import get_supabase_client
from app.middleware.auth import get_current_user, require_admin, UserContext
from app.middleware.audit import audit_log
from app.models import (
    SubscriptionActivateRequest,
    SuccessMessage,
)
from app.services import subscription_service, activity_service

router = APIRouter(prefix="/api/v1/subscriptions", tags=["Subscriptions"])


@router.get("/plans")
async def list_plans(
    request: Request,
    user: UserContext = Depends(get_current_user),
):
    """Return available subscription plans with limits and pricing."""
    settings = get_settings()
    plans = []

    for plan_name, limits in settings.PLAN_LIMITS.items():
        plans.append({
            "name": plan_name,
            "limits": limits,
            "price": 0.0 if plan_name == "free" else 19.90,
            "currency": "BRL",
            "billing_period": "monthly",
        })

    return {"plans": plans}


@router.post("/activate", response_model=SuccessMessage)
async def activate_subscription(
    body: SubscriptionActivateRequest,
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Manually activate a subscription (admin only, by payment_id).

    Looks up the payment log and activates the user's subscription.
    """
    # Look up payment log to find user_id
    payment_result = (
        db.table("payment_logs")
        .select("user_id, id")
        .eq("external_payment_id", body.payment_id)
        .execute()
    )

    if not payment_result.data:
        from app.exceptions import not_found
        raise not_found("Payment log")

    payment_log = payment_result.data[0]
    target_user_id = payment_log["user_id"]

    await subscription_service.activate_subscription(
        db,
        user_id=target_user_id,
        payment_log_id=str(payment_log["id"]),
        changed_by=f"admin:{user.id}",
        reason=f"Manual activation by admin for payment {body.payment_id}",
    )

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="activate_subscription",
        resource="subscriptions",
        resource_id=target_user_id,
        new_data={"payment_id": body.payment_id, "target_user_id": target_user_id},
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="admin_activate_subscription",
        metadata={"target_user_id": target_user_id, "payment_id": body.payment_id},
    )

    return SuccessMessage(message=f"Subscription activated for user {target_user_id}.")
