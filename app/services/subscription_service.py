"""Subscription management service for PizzaCost Pro."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from supabase import Client

from app.config import get_settings
from app.exceptions import AppException, not_found, subscription_limit

logger = logging.getLogger(__name__)

# Resource key -> (table_name, limit_key)
_RESOURCE_MAP: dict[str, tuple[str, str]] = {
    "max_pizzas": ("pizzas", "max_pizzas"),
    "max_ingredients": ("insumos", "max_ingredients"),
    "max_tamanhos": ("tamanhos", "max_tamanhos"),
    "max_bordas": ("bordas", "max_bordas"),
    "max_combos": ("combos", "max_combos"),
    "max_calculator_uses": ("calculator_uses", "max_calculator_uses"),
}


# ---------------------------------------------------------------------------
# Plan configuration
# ---------------------------------------------------------------------------

def get_plan_limits(plan: str) -> dict:
    """Return the limits dict for a given plan (``free`` or ``paid``).

    Falls back to ``free`` if the plan is unknown.
    """
    settings = get_settings()
    return settings.PLAN_LIMITS.get(plan, settings.PLAN_LIMITS["free"])


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def get_subscription(db: Client, user_id: str) -> dict:
    """Return subscription details for a user.

    Returns a dict with ``status``, ``plan_limits``, ``expires_at``, and
    current resource usage counts.
    """
    profile = (
        db.table("profiles")
        .select("subscription_status, subscription_expires_at")
        .eq("id", user_id)
        .execute()
    )
    if not profile.data:
        raise not_found("Profile")

    prof = profile.data[0]
    status = prof["subscription_status"]
    limits = get_plan_limits(status)

    # Current usage
    usage: dict[str, int] = {}
    for resource_key, (table, _) in _RESOURCE_MAP.items():
        count_result = (
            db.table(table)
            .select("id", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        usage[resource_key] = count_result.count or 0

    return {
        "status": status,
        "expires_at": prof.get("subscription_expires_at"),
        "plan_limits": limits,
        "usage": usage,
    }


# ---------------------------------------------------------------------------
# Limit check
# ---------------------------------------------------------------------------

async def check_limit(db: Client, user_id: str, resource: str) -> None:
    """Raise ``AppException`` if the user has reached their plan limit for *resource*.

    Args:
        resource: One of ``max_pizzas``, ``max_ingredients``, ``max_tamanhos``,
                  ``max_bordas``, ``max_combos``, ``max_calculator_uses``.

    Raises:
        AppException: With code ``SUBSCRIPTION_LIMIT`` when limit is exceeded.
                      A limit of 0 means the resource is fully blocked.
    """
    if resource not in _RESOURCE_MAP:
        return  # Unknown resource -- skip check

    table, limit_key = _RESOURCE_MAP[resource]

    # Get user plan
    profile = (
        db.table("profiles")
        .select("subscription_status")
        .eq("id", user_id)
        .execute()
    )
    if not profile.data:
        raise not_found("Profile")

    plan = profile.data[0]["subscription_status"]
    limits = get_plan_limits(plan)
    max_allowed = limits.get(limit_key, 0)

    # -1 means unlimited
    if max_allowed == -1:
        return

    # 0 means fully blocked for this plan
    if max_allowed == 0:
        raise subscription_limit(
            f"O recurso {resource.replace('max_', '')} nao esta disponivel "
            f"no plano {plan}. Faca upgrade para desbloquear."
        )

    # Count current
    count_result = (
        db.table(table)
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    current = count_result.count or 0

    if current >= max_allowed:
        raise subscription_limit(
            f"Voce atingiu o limite de {max_allowed} {resource.replace('max_', '')} "
            f"no plano {plan}. Faca upgrade para continuar."
        )


# ---------------------------------------------------------------------------
# Activate / Deactivate
# ---------------------------------------------------------------------------

async def activate_subscription(
    db: Client,
    user_id: str,
    payment_log_id: str | None = None,
    changed_by: str | None = None,
    reason: str = "payment_approved",
) -> None:
    """Activate a paid subscription for the user.

    - Updates ``profiles.subscription_status`` to ``paid``.
    - Sets ``subscription_expires_at`` to 30 days from now.
    - Inserts a ``subscription_history`` record.
    - Sends a confirmation email (best-effort).
    """
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(days=30)).isoformat()

    # Fetch current status for accurate history record
    profile_result = (
        db.table("profiles")
        .select("subscription_status")
        .eq("id", user_id)
        .execute()
    )
    old_status = "free"
    if profile_result.data:
        old_status = profile_result.data[0].get("subscription_status", "free")

    db.table("profiles").update(
        {
            "subscription_status": "paid",
            "subscription_expires_at": expires_at,
        }
    ).eq("id", user_id).execute()

    db.table("subscription_history").insert(
        {
            "user_id": user_id,
            "old_status": old_status,
            "new_status": "paid",
            "payment_log_id": payment_log_id,
            "changed_by": changed_by or "system",
            "reason": reason,
            "created_at": now.isoformat(),
        }
    ).execute()

    # Send confirmation email (best-effort)
    try:
        from app.services.email_service import send_transactional

        await send_transactional(
            db,
            user_id=user_id,
            template_slug="subscription_activated",
            variables={"expires_at": expires_at},
        )
    except Exception:
        logger.warning("Subscription activation email failed for user %s", user_id)


async def deactivate_subscription(
    db: Client,
    user_id: str,
    reason: str = "subscription_expired",
) -> None:
    """Deactivate a user's paid subscription back to the free plan.

    - Updates ``profiles.subscription_status`` to ``free``.
    - Clears ``subscription_expires_at``.
    - Inserts a ``subscription_history`` record.
    """
    now = datetime.now(timezone.utc)

    # Fetch current status for accurate history record
    profile_result = (
        db.table("profiles")
        .select("subscription_status")
        .eq("id", user_id)
        .execute()
    )
    old_status = "paid"
    if profile_result.data:
        old_status = profile_result.data[0].get("subscription_status", "paid")

    db.table("profiles").update(
        {
            "subscription_status": "free",
            "subscription_expires_at": None,
        }
    ).eq("id", user_id).execute()

    db.table("subscription_history").insert(
        {
            "user_id": user_id,
            "old_status": old_status,
            "new_status": "free",
            "changed_by": "system",
            "reason": reason,
            "created_at": now.isoformat(),
        }
    ).execute()

    # Send notification email (best-effort)
    try:
        from app.services.email_service import send_transactional

        await send_transactional(
            db,
            user_id=user_id,
            template_slug="subscription_deactivated",
            variables={},
        )
    except Exception:
        logger.warning("Subscription deactivation email failed for user %s", user_id)
