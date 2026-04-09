"""LGPD (Brazilian data-protection law) compliance service for PizzaCost Pro."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from supabase import Client

from app.exceptions import AppException, not_found

logger = logging.getLogger(__name__)

# Tables that hold user PII / user-scoped data
_USER_TABLES = [
    "profiles",
    "insumos",
    "tamanhos",
    "bordas",
    "pizzas",
    "combos",
    "email_preferences",
    "email_sends",
    "email_sequence_enrollments",
    "consent_logs",
    "subscription_history",
    "payment_logs",
    "user_activity",
    "audit_logs",
    "lgpd_requests",
]


# ---------------------------------------------------------------------------
# Data export
# ---------------------------------------------------------------------------

async def request_data_export(db: Client, user_id: str) -> dict:
    """Create an LGPD data-export request.

    Returns:
        The newly-created ``lgpd_requests`` row.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Prevent duplicate pending requests
    existing = (
        db.table("lgpd_requests")
        .select("id")
        .eq("user_id", user_id)
        .eq("type", "data_export")
        .eq("status", "pending")
        .execute()
    )
    if existing.data:
        raise AppException(
            code="DUPLICATE_REQUEST",
            message="A data export request is already pending.",
            status=409,
        )

    result = db.table("lgpd_requests").insert(
        {
            "user_id": user_id,
            "type": "data_export",
            "status": "pending",
            "created_at": now,
        }
    ).execute()
    return result.data[0]


async def execute_data_export(db: Client, request_id: str) -> None:
    """Execute a data-export request: gather all user data, upload JSON to
    Supabase Storage, and update the request with the download URL.
    """
    # Load request
    req_result = (
        db.table("lgpd_requests")
        .select("*")
        .eq("id", request_id)
        .execute()
    )
    if not req_result.data:
        raise not_found("LGPD request")

    request = req_result.data[0]
    user_id = request["user_id"]

    # Gather ALL user data
    export_data: dict = {}
    for table in _USER_TABLES:
        try:
            table_result = (
                db.table(table)
                .select("*")
                .eq("user_id" if table != "profiles" else "id", user_id)
                .execute()
            )
            export_data[table] = table_result.data
        except Exception:
            logger.warning("Could not export table '%s' for user %s", table, user_id)
            export_data[table] = []

    # Serialize to JSON
    json_bytes = json.dumps(export_data, indent=2, default=str, ensure_ascii=False).encode("utf-8")

    # Upload to Supabase Storage
    filename = f"lgpd-exports/{user_id}/{request_id}.json"
    try:
        db.storage.from_("lgpd").upload(
            filename,
            json_bytes,
            {"content-type": "application/json"},
        )
        # Create a signed URL valid for 7 days
        signed = db.storage.from_("lgpd").create_signed_url(filename, 60 * 60 * 24 * 7)
        download_url = signed.get("signedURL") or signed.get("signedUrl", "")
    except Exception:
        logger.exception("Failed to upload LGPD export for request %s", request_id)
        db.table("lgpd_requests").update(
            {"status": "failed"}
        ).eq("id", request_id).execute()
        return

    # Update request
    now = datetime.now(timezone.utc).isoformat()
    db.table("lgpd_requests").update(
        {
            "status": "completed",
            "download_url": download_url,
            "completed_at": now,
        }
    ).eq("id", request_id).execute()

    # Notify user
    try:
        from app.services.email_service import send_transactional

        await send_transactional(
            db,
            user_id=user_id,
            template_slug="data_export_ready",
            variables={"download_url": download_url},
        )
    except Exception:
        logger.warning("Data export notification email failed for user %s", user_id)


# ---------------------------------------------------------------------------
# Account deletion
# ---------------------------------------------------------------------------

async def request_account_deletion(db: Client, user_id: str) -> dict:
    """Create an account-deletion request and send a confirmation email.

    The actual deletion is deferred and executed by ``execute_account_deletion``
    after a cooling-off period.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Prevent duplicate pending requests
    existing = (
        db.table("lgpd_requests")
        .select("id")
        .eq("user_id", user_id)
        .eq("type", "account_deletion")
        .eq("status", "pending")
        .execute()
    )
    if existing.data:
        raise AppException(
            code="DUPLICATE_REQUEST",
            message="An account deletion request is already pending.",
            status=409,
        )

    result = db.table("lgpd_requests").insert(
        {
            "user_id": user_id,
            "type": "account_deletion",
            "status": "pending",
            "created_at": now,
        }
    ).execute()

    # Send confirmation email
    try:
        from app.services.email_service import send_transactional

        await send_transactional(
            db,
            user_id=user_id,
            template_slug="account_deletion_requested",
            variables={"deletion_date": (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%d/%m/%Y")},
        )
    except Exception:
        logger.warning("Account deletion confirmation email failed for user %s", user_id)

    return result.data[0]


async def execute_account_deletion(db: Client, request_id: str) -> None:
    """Execute account deletion.

    Steps:
        1. Soft-delete the profile (``deleted_at``).
        2. Anonymize PII in ``audit_logs``.
        3. Mark request as completed.

    Hard-delete of all user data is intended to run 30 days after the
    soft-delete via a scheduled job.
    """
    req_result = (
        db.table("lgpd_requests")
        .select("*")
        .eq("id", request_id)
        .execute()
    )
    if not req_result.data:
        raise not_found("LGPD request")

    request = req_result.data[0]
    user_id = request["user_id"]
    now = datetime.now(timezone.utc).isoformat()

    # 1. Soft-delete profile
    db.table("profiles").update(
        {
            "deleted_at": now,
            "email": f"deleted_{user_id}@anon.local",
            "nome_loja": "Conta removida",
            "telefone": None,
        }
    ).eq("id", user_id).execute()

    # 2. Anonymize PII in audit_logs
    audit_result = (
        db.table("audit_logs")
        .select("id")
        .eq("user_id", user_id)
        .execute()
    )
    for log_entry in audit_result.data:
        db.table("audit_logs").update(
            {
                "old_data": None,
                "new_data": None,
                "ip_address": None,
            }
        ).eq("id", log_entry["id"]).execute()

    # 3. Mark request as completed
    db.table("lgpd_requests").update(
        {
            "status": "completed",
            "completed_at": now,
        }
    ).eq("id", request_id).execute()

    logger.info("Account deletion executed for user %s (request %s)", user_id, request_id)


# ---------------------------------------------------------------------------
# Consent management
# ---------------------------------------------------------------------------

async def get_consent_log(db: Client, user_id: str) -> list[dict]:
    """Return all consent log entries for a user, newest first."""
    result = (
        db.table("consent_logs")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


async def record_consent(
    db: Client,
    user_id: str,
    consent_type: str,
    granted: bool,
    ip: str | None = None,
    user_agent: str | None = None,
    policy_version: str = "1.0",
) -> None:
    """Record a consent action in ``consent_logs``."""
    now = datetime.now(timezone.utc).isoformat()

    db.table("consent_logs").insert(
        {
            "user_id": user_id,
            "consent_type": consent_type,
            "granted": granted,
            "ip_address": ip,
            "user_agent": user_agent,
            "policy_version": policy_version,
            "created_at": now,
        }
    ).execute()

    # If marketing consent changed, update email_preferences
    if consent_type == "marketing":
        db.table("email_preferences").update(
            {"marketing_opt_in": granted}
        ).eq("user_id", user_id).execute()
