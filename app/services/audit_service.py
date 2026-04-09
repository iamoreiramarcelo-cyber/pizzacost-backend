"""Audit logging service for PizzaCost Pro."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from supabase import Client

logger = logging.getLogger(__name__)


async def log(
    db: Client,
    user_id: str,
    action: str,
    resource: str,
    resource_id: str | None = None,
    old_data: dict | None = None,
    new_data: dict | None = None,
    ip: str | None = None,
) -> None:
    """Insert an audit-log entry.

    Args:
        db: Supabase client.
        user_id: The user who performed the action.
        action: Action verb (``create``, ``update``, ``delete``, ``login``,
                ``impersonate``, etc.).
        resource: Table or resource name.
        resource_id: Optional primary key of the affected resource.
        old_data: Previous state (for updates/deletes).
        new_data: New state (for creates/updates).
        ip: Client IP address.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Ensure data is JSON-serialisable
    def _safe_json(data: dict | None) -> dict | None:
        if data is None:
            return None
        try:
            json.dumps(data, default=str)
            return data
        except (TypeError, ValueError):
            return {"_serialization_error": True}

    try:
        db.table("audit_logs").insert(
            {
                "user_id": user_id,
                "action": action,
                "resource": resource,
                "resource_id": resource_id,
                "old_data": _safe_json(old_data),
                "new_data": _safe_json(new_data),
                "ip_address": ip,
                "created_at": now,
            }
        ).execute()
    except Exception:
        # Audit logging should never break the main flow
        logger.exception(
            "Failed to write audit log: user=%s action=%s resource=%s",
            user_id,
            action,
            resource,
        )


async def list_logs(
    db: Client,
    page: int = 1,
    per_page: int = 20,
    user_id: str | None = None,
    resource: str | None = None,
    action: str | None = None,
) -> tuple[list[dict], int]:
    """Return a paginated, optionally filtered, list of audit-log entries.

    Returns:
        A tuple of ``(items, total_count)``.
    """
    offset = (page - 1) * per_page

    # Count query
    count_query = db.table("audit_logs").select("id", count="exact")
    if user_id:
        count_query = count_query.eq("user_id", user_id)
    if resource:
        count_query = count_query.eq("resource", resource)
    if action:
        count_query = count_query.eq("action", action)
    count_result = count_query.execute()
    total = count_result.count or 0

    # Data query
    data_query = db.table("audit_logs").select("*")
    if user_id:
        data_query = data_query.eq("user_id", user_id)
    if resource:
        data_query = data_query.eq("resource", resource)
    if action:
        data_query = data_query.eq("action", action)
    data_query = data_query.order("created_at", desc=True).range(offset, offset + per_page - 1)
    result = data_query.execute()

    return result.data, total
