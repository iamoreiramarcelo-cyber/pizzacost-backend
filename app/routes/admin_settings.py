"""Admin settings routes for PizzaCost Pro."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.database import get_supabase_client
from app.exceptions import not_found
from app.middleware.auth import require_super_admin, UserContext
from app.middleware.audit import audit_log
from app.models import AdminSettingsUpdate, SuccessMessage
from app.services import activity_service

router = APIRouter(prefix="/api/v1/admin/settings", tags=["Admin - Settings"])


@router.get("")
async def list_settings(
    request: Request,
    user: UserContext = Depends(require_super_admin),
    db: Client = Depends(get_supabase_client),
):
    """List all system settings."""
    result = (
        db.table("system_settings")
        .select("*")
        .order("key")
        .execute()
    )
    return {"settings": result.data}


@router.get("/{key}")
async def get_setting(
    key: str,
    request: Request,
    user: UserContext = Depends(require_super_admin),
    db: Client = Depends(get_supabase_client),
):
    """Get a specific system setting by key."""
    result = (
        db.table("system_settings")
        .select("*")
        .eq("key", key)
        .execute()
    )
    if not result.data:
        raise not_found("Setting")
    return result.data[0]


@router.put("/{key}", response_model=SuccessMessage)
async def update_setting(
    key: str,
    body: AdminSettingsUpdate,
    request: Request,
    user: UserContext = Depends(require_super_admin),
    db: Client = Depends(get_supabase_client),
):
    """Update a system setting by key."""
    now = datetime.now(timezone.utc).isoformat()

    # Check if setting exists
    existing = (
        db.table("system_settings")
        .select("*")
        .eq("key", key)
        .execute()
    )

    old_data = existing.data[0] if existing.data else None

    if existing.data:
        db.table("system_settings").update(
            {"value": body.value, "updated_at": now, "updated_by": user.id}
        ).eq("key", key).execute()
    else:
        db.table("system_settings").insert(
            {
                "key": key,
                "value": body.value,
                "created_at": now,
                "updated_at": now,
                "updated_by": user.id,
            }
        ).execute()

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="update",
        resource="system_settings",
        resource_id=key,
        old_data=old_data,
        new_data={"key": key, "value": body.value},
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="admin_update_setting",
        metadata={"key": key},
    )

    return SuccessMessage(message=f"Setting '{key}' updated successfully.")
