"""Admin service for PizzaCost Pro back-office."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from supabase import Client

from app.exceptions import AppException, not_found
from app.utils.sanitize import sanitize_string

logger = logging.getLogger(__name__)

MONTHLY_PRICE = 19.90  # BRL


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

async def get_dashboard(db: Client) -> dict:
    """Return admin dashboard metrics.

    Returns a dict with:
        - ``total_users``
        - ``paid_users``
        - ``free_users``
        - ``mrr`` (Monthly Recurring Revenue)
        - ``new_signups_30d``
        - ``churn_rate``
    """
    # Total users
    total_result = db.table("profiles").select("id", count="exact").execute()
    total_users = total_result.count or 0

    # Paid users
    paid_result = (
        db.table("profiles")
        .select("id", count="exact")
        .eq("subscription_status", "paid")
        .execute()
    )
    paid_users = paid_result.count or 0

    free_users = total_users - paid_users
    mrr = round(paid_users * MONTHLY_PRICE, 2)

    # New signups in last 30 days
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    new_result = (
        db.table("profiles")
        .select("id", count="exact")
        .gte("created_at", thirty_days_ago)
        .execute()
    )
    new_signups_30d = new_result.count or 0

    # Churn rate: deactivations in last 30 days / total paid at start of period
    churn_result = (
        db.table("subscription_history")
        .select("id", count="exact")
        .eq("new_status", "free")
        .gte("created_at", thirty_days_ago)
        .execute()
    )
    churned = churn_result.count or 0
    # Approximate: paid at start = current paid + churned
    paid_at_start = paid_users + churned
    churn_rate = round((churned / paid_at_start * 100), 1) if paid_at_start > 0 else 0.0

    return {
        "total_users": total_users,
        "paid_users": paid_users,
        "free_users": free_users,
        "mrr": mrr,
        "new_signups_30d": new_signups_30d,
        "churn_rate": churn_rate,
    }


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

async def list_users(
    db: Client,
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
    status_filter: str | None = None,
) -> tuple[list[dict], int]:
    """Return a paginated, optionally filtered, list of user profiles."""
    offset = (page - 1) * per_page

    # Sanitize search to prevent PostgREST filter injection
    # Remove characters that have special meaning in PostgREST filters
    if search:
        safe_search = search.replace(",", "").replace(".", "").replace("(", "").replace(")", "")
    else:
        safe_search = None

    # Build count query
    count_query = db.table("profiles").select("id", count="exact")
    if status_filter:
        count_query = count_query.eq("subscription_status", status_filter)
    if safe_search:
        count_query = count_query.or_(f"email.ilike.%{safe_search}%,nome_loja.ilike.%{safe_search}%")
    count_result = count_query.execute()
    total = count_result.count or 0

    # Build data query
    data_query = db.table("profiles").select("*")
    if status_filter:
        data_query = data_query.eq("subscription_status", status_filter)
    if safe_search:
        data_query = data_query.or_(f"email.ilike.%{safe_search}%,nome_loja.ilike.%{safe_search}%")
    data_query = data_query.order("created_at", desc=True).range(offset, offset + per_page - 1)
    result = data_query.execute()

    return result.data, total


async def create_user(db: Client, data: dict) -> dict:
    """Admin-create a new user (auth user + profile).

    ``data`` should contain ``email``, ``password``, ``nome_loja``,
    ``telefone`` (optional), ``role`` (optional, default ``user``).
    """
    from app.services.auth_service import create_profile

    try:
        auth_response = db.auth.admin.create_user(
            {
                "email": data["email"],
                "password": data["password"],
                "email_confirm": True,
            }
        )
        user_id = str(auth_response.user.id)
    except Exception as exc:
        error_msg = str(exc)
        if "already" in error_msg.lower() or "duplicate" in error_msg.lower():
            raise AppException(
                code="DUPLICATE_EMAIL",
                message="An account with this email already exists.",
                status=409,
            )
        logger.exception("Admin: failed to create auth user")
        raise AppException(
            code="AUTH_ERROR",
            message="Failed to create user account.",
            status=500,
        )

    profile = await create_profile(
        db,
        user_id=user_id,
        email=data["email"],
        nome_loja=data.get("nome_loja", ""),
        telefone=data.get("telefone"),
        role=data.get("role", "user"),
    )
    return profile


async def update_user(db: Client, user_id: str, data: dict) -> dict:
    """Admin-update a user profile.

    ``data`` may contain ``nome_loja``, ``telefone``, ``role``,
    ``subscription_status``.
    """
    update_payload: dict = {}
    if data.get("nome_loja") is not None:
        update_payload["nome_loja"] = sanitize_string(data["nome_loja"])
    if data.get("telefone") is not None:
        update_payload["telefone"] = sanitize_string(data["telefone"])
    if data.get("role") is not None:
        update_payload["role"] = data["role"]
    if data.get("subscription_status") is not None:
        update_payload["subscription_status"] = data["subscription_status"]

    if not update_payload:
        # Fetch and return current
        result = db.table("profiles").select("*").eq("id", user_id).execute()
        if not result.data:
            raise not_found("User")
        return result.data[0]

    result = db.table("profiles").update(update_payload).eq("id", user_id).execute()
    if not result.data:
        raise not_found("User")
    return result.data[0]


async def disable_user(db: Client, user_id: str) -> None:
    """Soft-delete a user by setting ``deleted_at``."""
    now = datetime.now(timezone.utc).isoformat()
    result = (
        db.table("profiles")
        .update({"deleted_at": now})
        .eq("id", user_id)
        .execute()
    )
    if not result.data:
        raise not_found("User")

    logger.info("User %s soft-deleted by admin", user_id)


# ---------------------------------------------------------------------------
# Activity & Impersonation
# ---------------------------------------------------------------------------

async def get_user_activity(
    db: Client,
    user_id: str,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """Return paginated activity log for a specific user."""
    offset = (page - 1) * per_page

    count_result = (
        db.table("user_activity")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    total = count_result.count or 0

    result = (
        db.table("user_activity")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .range(offset, offset + per_page - 1)
        .execute()
    )
    return result.data, total


async def impersonate_user(
    db: Client,
    admin_id: str,
    target_user_id: str,
) -> dict:
    """Read-only impersonation: return the target user's full data.

    Logs the impersonation in ``audit_logs``.
    """
    from app.services.audit_service import log as audit_log

    # Verify target user exists
    profile_result = db.table("profiles").select("*").eq("id", target_user_id).execute()
    if not profile_result.data:
        raise not_found("User")

    profile = profile_result.data[0]

    # Gather user data
    insumos = db.table("insumos").select("*").eq("user_id", target_user_id).execute()
    tamanhos = db.table("tamanhos").select("*").eq("user_id", target_user_id).execute()
    bordas = db.table("bordas").select("*").eq("user_id", target_user_id).execute()
    pizzas = db.table("pizzas").select("*").eq("user_id", target_user_id).execute()
    combos = db.table("combos").select("*").eq("user_id", target_user_id).execute()

    # Audit log
    await audit_log(
        db,
        user_id=admin_id,
        action="impersonate",
        resource="profiles",
        resource_id=target_user_id,
    )

    return {
        "profile": profile,
        "insumos": insumos.data,
        "tamanhos": tamanhos.data,
        "bordas": bordas.data,
        "pizzas": pizzas.data,
        "combos": combos.data,
    }
