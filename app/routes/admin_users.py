"""Admin user management routes for PizzaCost Pro."""

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.database import get_supabase_client
from app.middleware.auth import require_admin, UserContext
from app.middleware.audit import audit_log
from app.models import (
    AdminUserCreate,
    AdminUserListItem,
    AdminUserUpdate,
    PaginatedResponse,
    PaginationMeta,
    SuccessMessage,
)
from app.services import admin_service, activity_service

router = APIRouter(prefix="/api/v1/admin/users", tags=["Admin - Users"])


@router.get("", response_model=PaginatedResponse[AdminUserListItem])
async def list_users(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
    status: str | None = None,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """List all users with optional search and status filter."""
    items, total = await admin_service.list_users(
        db, page=page, per_page=per_page, search=search, status_filter=status
    )
    return PaginatedResponse(
        data=[AdminUserListItem(**item) for item in items],
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
    )


@router.post("", status_code=201)
async def create_user(
    body: AdminUserCreate,
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Create a new user/store (admin action)."""
    data = body.model_dump()
    profile = await admin_service.create_user(db, data=data)

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="admin_create_user",
        resource="profiles",
        resource_id=str(profile["id"]),
        new_data={"email": data["email"], "nome_loja": data.get("nome_loja")},
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="admin_create_user",
        metadata={"created_user_id": str(profile["id"])},
    )

    return profile


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Get detailed information about a specific user."""
    result = db.table("profiles").select("*").eq("id", user_id).execute()
    if not result.data:
        from app.exceptions import not_found
        raise not_found("User")
    return result.data[0]


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    body: AdminUserUpdate,
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Update a user's profile (admin action)."""
    data = body.model_dump(exclude_none=True)

    old_result = db.table("profiles").select("*").eq("id", user_id).execute()
    old_data = old_result.data[0] if old_result.data else None

    profile = await admin_service.update_user(db, user_id=user_id, data=data)

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="admin_update_user",
        resource="profiles",
        resource_id=user_id,
        old_data=old_data,
        new_data=profile,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="admin_update_user",
        metadata={"target_user_id": user_id},
    )

    return profile


@router.delete("/{user_id}", response_model=SuccessMessage)
async def disable_user(
    user_id: str,
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Disable/soft-delete a user."""
    await admin_service.disable_user(db, user_id=user_id)

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="admin_disable_user",
        resource="profiles",
        resource_id=user_id,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="admin_disable_user",
        metadata={"target_user_id": user_id},
    )

    return SuccessMessage(message=f"User {user_id} has been disabled.")


@router.get("/{user_id}/activity")
async def get_user_activity(
    user_id: str,
    request: Request,
    page: int = 1,
    per_page: int = 20,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Get a user's activity log."""
    items, total = await admin_service.get_user_activity(
        db, user_id=user_id, page=page, per_page=per_page
    )
    return PaginatedResponse(
        data=items,
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
    )


@router.get("/{user_id}/subscription-history")
async def get_subscription_history(
    user_id: str,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Get subscription change history for a user."""
    result = db.table("subscription_history").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    return {"data": result.data or []}


@router.put("/{user_id}/subscription")
async def update_subscription(
    user_id: str,
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Activate or cancel subscription for a user."""
    body = await request.json()
    action = body.get("action")  # "activate" or "cancel"

    profile = db.table("profiles").select("subscription_status").eq("id", user_id).single().execute()
    old_status = profile.data.get("subscription_status", "free") if profile.data else "free"

    if action == "activate":
        db.table("profiles").update({"subscription_status": "paid"}).eq("id", user_id).execute()
        new_status = "paid"
    elif action == "cancel":
        db.table("profiles").update({"subscription_status": "free"}).eq("id", user_id).execute()
        new_status = "free"
    elif action == "disable":
        from datetime import datetime
        db.table("profiles").update({"deleted_at": datetime.utcnow().isoformat()}).eq("id", user_id).execute()
        return {"data": {"message": "Conta desativada."}}
    else:
        return {"error": {"code": "INVALID_ACTION", "message": "Acao invalida."}}

    db.table("subscription_history").insert({
        "user_id": user_id,
        "old_status": old_status,
        "new_status": new_status,
        "reason": f"admin_manual_{action}",
        "changed_by": user.id,
    }).execute()

    await audit_log(db, user.id, f"ADMIN_{action.upper()}_SUBSCRIPTION", "profiles", user_id)
    return {"data": {"status": new_status, "message": f"Assinatura {new_status}."}}


@router.get("/{user_id}/payments")
async def get_user_payments(
    user_id: str,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Get payment history for a user."""
    result = db.table("payment_logs").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(50).execute()
    return {"data": result.data or []}


@router.get("/{user_id}/data-summary")
async def get_user_data_summary(
    user_id: str,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Get summary of user's registered data (counts)."""
    insumos = db.table("insumos").select("id", count="exact").eq("user_id", user_id).execute()
    tamanhos = db.table("tamanhos").select("id", count="exact").eq("user_id", user_id).execute()
    bordas = db.table("bordas").select("id", count="exact").eq("user_id", user_id).execute()
    pizzas = db.table("pizzas").select("id", count="exact").eq("user_id", user_id).execute()
    combos = db.table("combos").select("id", count="exact").eq("user_id", user_id).execute()

    return {"data": {
        "insumos": insumos.count or 0,
        "tamanhos": tamanhos.count or 0,
        "bordas": bordas.count or 0,
        "sabores": pizzas.count or 0,
        "combos": combos.count or 0,
    }}


@router.post("/{user_id}/impersonate")
async def impersonate_user(
    user_id: str,
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Read-only impersonation: returns the target user's full data."""
    data = await admin_service.impersonate_user(
        db, admin_id=user.id, target_user_id=user_id
    )

    await activity_service.track(
        db, user_id=user.id, action="admin_impersonate",
        metadata={"target_user_id": user_id},
    )

    return data
