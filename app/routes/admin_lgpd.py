"""Admin LGPD (data protection) routes for PizzaCost Pro."""

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.database import get_supabase_client
from app.exceptions import not_found
from app.middleware.auth import require_admin, UserContext
from app.middleware.audit import audit_log
from app.models import (
    AuditLogResponse,
    LgpdRequestResponse,
    PaginatedResponse,
    PaginationMeta,
    SuccessMessage,
)
from app.services import lgpd_service, activity_service

router = APIRouter(prefix="/api/v1/admin/lgpd", tags=["Admin - LGPD"])


@router.get("/requests", response_model=PaginatedResponse[LgpdRequestResponse])
async def list_lgpd_requests(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    status: str | None = None,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """List LGPD requests (exports and deletions) with optional status filter."""
    offset = (page - 1) * per_page

    # Count query
    count_query = db.table("lgpd_requests").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    count_result = count_query.execute()
    total = count_result.count or 0

    # Data query with joined user email
    data_query = db.table("lgpd_requests").select("*, profiles!inner(email)")
    if status:
        data_query = data_query.eq("status", status)
    data_query = data_query.order("created_at", desc=True).range(offset, offset + per_page - 1)
    result = data_query.execute()

    # Flatten the joined data
    items = []
    for row in result.data:
        profile_data = row.pop("profiles", {})
        row["user_email"] = profile_data.get("email", "") if isinstance(profile_data, dict) else ""
        row["request_type"] = row.get("type", "")
        items.append(LgpdRequestResponse(**row))

    return PaginatedResponse(
        data=items,
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
    )


@router.put("/requests/{request_id}/process", response_model=SuccessMessage)
async def process_lgpd_request(
    request_id: str,
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Process a pending LGPD request (execute export or deletion)."""
    # Load the request
    req_result = (
        db.table("lgpd_requests")
        .select("*")
        .eq("id", request_id)
        .execute()
    )
    if not req_result.data:
        raise not_found("LGPD request")

    lgpd_request = req_result.data[0]
    request_type = lgpd_request.get("type", "")

    if request_type == "data_export":
        await lgpd_service.execute_data_export(db, request_id=request_id)
        message = "Data export processed successfully."
    elif request_type == "account_deletion":
        await lgpd_service.execute_account_deletion(db, request_id=request_id)
        message = "Account deletion processed successfully."
    else:
        message = f"Unknown request type: {request_type}"

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="process_lgpd_request",
        resource="lgpd_requests",
        resource_id=request_id,
        new_data={"type": request_type, "status": "completed"},
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="admin_process_lgpd_request",
        metadata={"request_id": request_id, "type": request_type},
    )

    return SuccessMessage(message=message)


@router.get("/consent-logs")
async def list_consent_logs(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    user_id: str | None = None,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """List consent logs with optional user filter."""
    offset = (page - 1) * per_page

    # Count query
    count_query = db.table("consent_logs").select("id", count="exact")
    if user_id:
        count_query = count_query.eq("user_id", user_id)
    count_result = count_query.execute()
    total = count_result.count or 0

    # Data query
    data_query = db.table("consent_logs").select("*")
    if user_id:
        data_query = data_query.eq("user_id", user_id)
    data_query = data_query.order("created_at", desc=True).range(offset, offset + per_page - 1)
    result = data_query.execute()

    return PaginatedResponse(
        data=result.data,
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
    )


@router.get("/audit-logs", response_model=PaginatedResponse[AuditLogResponse])
async def list_audit_logs(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    user_id: str | None = None,
    resource: str | None = None,
    action: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """List audit logs with filters (user, resource, action, date range)."""
    offset = (page - 1) * per_page

    # Count query
    count_query = db.table("audit_logs").select("id", count="exact")
    if user_id:
        count_query = count_query.eq("user_id", user_id)
    if resource:
        count_query = count_query.eq("resource", resource)
    if action:
        count_query = count_query.eq("action", action)
    if date_from:
        count_query = count_query.gte("created_at", date_from)
    if date_to:
        count_query = count_query.lte("created_at", date_to)
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
    if date_from:
        data_query = data_query.gte("created_at", date_from)
    if date_to:
        data_query = data_query.lte("created_at", date_to)
    data_query = data_query.order("created_at", desc=True).range(offset, offset + per_page - 1)
    result = data_query.execute()

    return PaginatedResponse(
        data=[AuditLogResponse(**log) for log in result.data],
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
    )
