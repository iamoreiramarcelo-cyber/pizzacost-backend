import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request
from supabase import Client

from app.database import get_supabase_client

logger = logging.getLogger("pizzacost.audit")


def _insert_audit_record(db: Client, record: dict[str, Any]) -> None:
    """Synchronous helper that performs the blocking Supabase insert."""
    db.table("audit_logs").insert(record).execute()


async def audit_log(
    db: Client,
    user_id: str,
    action: str,
    resource: str,
    resource_id: Optional[str] = None,
    old_data: Optional[dict[str, Any]] = None,
    new_data: Optional[dict[str, Any]] = None,
    ip: Optional[str] = None,
) -> None:
    """Insert an entry into the audit_logs table.

    Runs the synchronous Supabase call in a thread to avoid blocking the
    async event loop.
    """
    record = {
        "user_id": user_id,
        "action": action,
        "resource": resource,
        "resource_id": resource_id,
        "old_data": json.loads(json.dumps(old_data, default=str)) if old_data else None,
        "new_data": json.loads(json.dumps(new_data, default=str)) if new_data else None,
        "ip_address": ip,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        await asyncio.to_thread(_insert_audit_record, db, record)
    except Exception:
        logger.exception("Failed to write audit log: action=%s resource=%s", action, resource)


class AuditLogger:
    """Dependency class for audit logging within route handlers."""

    def __init__(self, request: Request):
        self.db = get_supabase_client()
        self.ip = request.client.host if request.client else None

    async def log(
        self,
        user_id: str,
        action: str,
        resource: str,
        resource_id: Optional[str] = None,
        old_data: Optional[dict[str, Any]] = None,
        new_data: Optional[dict[str, Any]] = None,
    ) -> None:
        await audit_log(
            db=self.db,
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            old_data=old_data,
            new_data=new_data,
            ip=self.ip,
        )
