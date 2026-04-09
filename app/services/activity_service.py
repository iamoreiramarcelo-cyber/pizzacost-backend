"""User activity tracking service for PizzaCost Pro."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from supabase import Client

logger = logging.getLogger(__name__)


async def track(
    db: Client,
    user_id: str,
    action: str,
    metadata: dict | None = None,
) -> None:
    """Record a user activity event.

    Args:
        db: Supabase client.
        user_id: The user who performed the action.
        action: A descriptive action string (e.g. ``login``, ``create_pizza``,
                ``export_pdf``).
        metadata: Optional dict with additional context.
    """
    now = datetime.now(timezone.utc).isoformat()

    try:
        db.table("user_activity").insert(
            {
                "user_id": user_id,
                "action": action,
                "metadata": metadata,
                "created_at": now,
            }
        ).execute()
    except Exception:
        # Activity tracking should never break the main flow
        logger.exception(
            "Failed to track activity: user=%s action=%s",
            user_id,
            action,
        )


async def get_last_activity(db: Client, user_id: str) -> datetime | None:
    """Return the timestamp of the user's most recent activity, or ``None``.

    Returns:
        A timezone-aware ``datetime`` or ``None`` if no activity exists.
    """
    result = (
        db.table("user_activity")
        .select("created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .range(0, 0)
        .execute()
    )
    if result.data:
        raw = result.data[0]["created_at"]
        if isinstance(raw, str):
            # Parse ISO format from Supabase
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return raw
    return None
