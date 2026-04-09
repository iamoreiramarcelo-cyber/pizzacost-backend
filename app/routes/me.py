"""User profile and account management routes for PizzaCost Pro."""

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.database import get_supabase_client
from app.middleware.auth import get_current_user, UserContext
from app.middleware.audit import audit_log
from app.models import (
    EmailPreferencesUpdate,
    ProfileResponse,
    ProfileUpdate,
    SubscriptionResponse,
    SuccessMessage,
)
from app.services import (
    auth_service,
    activity_service,
    lgpd_service,
    subscription_service,
)

router = APIRouter(prefix="/api/v1/me", tags=["Profile"])


@router.get("/", response_model=ProfileResponse)
async def get_profile(
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Get the current user's profile."""
    profile = await auth_service.get_user_profile(db, user_id=user.id)
    if not profile:
        from app.exceptions import not_found
        raise not_found("Profile")
    return ProfileResponse(**profile)


@router.put("/", response_model=ProfileResponse)
async def update_profile(
    body: ProfileUpdate,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Update the current user's profile (nome_loja, telefone)."""
    update_payload = body.model_dump(exclude_none=True)

    if not update_payload:
        profile = await auth_service.get_user_profile(db, user_id=user.id)
        return ProfileResponse(**profile)

    old_profile = await auth_service.get_user_profile(db, user_id=user.id)

    from app.utils.sanitize import sanitize_string
    if "nome_loja" in update_payload:
        update_payload["nome_loja"] = sanitize_string(update_payload["nome_loja"])
    if "telefone" in update_payload:
        update_payload["telefone"] = sanitize_string(update_payload["telefone"])

    result = (
        db.table("profiles")
        .update(update_payload)
        .eq("id", user.id)
        .execute()
    )
    updated_profile = result.data[0] if result.data else old_profile

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="update",
        resource="profiles",
        resource_id=user.id,
        old_data=old_profile,
        new_data=updated_profile,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="update_profile"
    )

    return ProfileResponse(**updated_profile)


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Get the current user's subscription details with plan limits."""
    sub = await subscription_service.get_subscription(db, user_id=user.id)
    return SubscriptionResponse(
        status=sub["status"],
        expires_at=sub.get("expires_at"),
        limits=sub["plan_limits"],
    )


@router.get("/email-preferences")
async def get_email_preferences(
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Get the current user's email preferences."""
    result = (
        db.table("email_preferences")
        .select("*")
        .eq("user_id", user.id)
        .execute()
    )
    if not result.data:
        return {
            "marketing_opt_in": False,
            "transactional_enabled": True,
        }
    prefs = result.data[0]
    return {
        "marketing_opt_in": prefs.get("marketing_opt_in", False),
        "transactional_enabled": prefs.get("transactional_enabled", True),
    }


@router.put("/email-preferences", response_model=SuccessMessage)
async def update_email_preferences(
    body: EmailPreferencesUpdate,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Update the current user's email preferences."""
    update_payload = {
        "marketing_opt_in": body.marketing_opt_in,
        "transactional_enabled": body.transactional_enabled,
    }

    # Upsert email preferences
    existing = (
        db.table("email_preferences")
        .select("user_id")
        .eq("user_id", user.id)
        .execute()
    )

    if existing.data:
        db.table("email_preferences").update(update_payload).eq("user_id", user.id).execute()
    else:
        db.table("email_preferences").insert(
            {"user_id": user.id, **update_payload}
        ).execute()

    # Record LGPD consent for marketing change
    ip = request.client.host if request.client else None
    await lgpd_service.record_consent(
        db,
        user_id=user.id,
        consent_type="marketing",
        granted=body.marketing_opt_in,
        ip=ip,
    )

    await audit_log(
        db=db,
        user_id=user.id,
        action="update",
        resource="email_preferences",
        new_data=update_payload,
        ip=ip,
    )

    return SuccessMessage(message="Email preferences updated successfully.")


@router.post("/data-export", status_code=202)
async def request_data_export(
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Request a LGPD data export. Returns the request ID for tracking."""
    lgpd_request = await lgpd_service.request_data_export(db, user_id=user.id)

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="create",
        resource="lgpd_requests",
        resource_id=str(lgpd_request["id"]),
        new_data={"type": "data_export"},
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="request_data_export"
    )

    return {
        "message": "Data export request created. You will be notified by email when ready.",
        "request_id": str(lgpd_request["id"]),
        "status": lgpd_request["status"],
    }


@router.delete("/account", status_code=202)
async def request_account_deletion(
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Request LGPD account deletion. Subject to a cooling-off period."""
    lgpd_request = await lgpd_service.request_account_deletion(db, user_id=user.id)

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="create",
        resource="lgpd_requests",
        resource_id=str(lgpd_request["id"]),
        new_data={"type": "account_deletion"},
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="request_account_deletion"
    )

    return {
        "message": "Account deletion request created. You will receive a confirmation email.",
        "request_id": str(lgpd_request["id"]),
        "status": lgpd_request["status"],
    }


@router.get("/data-export/{request_id}")
async def check_data_export(
    request_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Check the status of a data export request. Returns download URL if ready."""
    result = (
        db.table("lgpd_requests")
        .select("*")
        .eq("id", request_id)
        .eq("user_id", user.id)
        .eq("type", "data_export")
        .execute()
    )
    if not result.data:
        from app.exceptions import not_found
        raise not_found("Data export request")

    lgpd_request = result.data[0]
    response = {
        "request_id": str(lgpd_request["id"]),
        "status": lgpd_request["status"],
        "created_at": lgpd_request["created_at"],
    }

    if lgpd_request.get("download_url"):
        response["download_url"] = lgpd_request["download_url"]
    if lgpd_request.get("completed_at"):
        response["completed_at"] = lgpd_request["completed_at"]

    return response
