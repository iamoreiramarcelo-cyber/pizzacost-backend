"""Admin email management routes for PizzaCost Pro."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.database import get_supabase_client
from app.middleware.auth import require_admin, UserContext
from app.middleware.audit import audit_log
from app.models import (
    EmailSequenceCreate,
    EmailSequenceResponse,
    EmailSequenceUpdate,
    EmailTemplateCreate,
    EmailTemplateResponse,
    EmailTemplateUpdate,
    PaginatedResponse,
    PaginationMeta,
    SuccessMessage,
)
from app.services import email_service, activity_service
from app.exceptions import not_found

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/emails", tags=["Admin - Emails"])


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


@router.get("/templates", response_model=list[EmailTemplateResponse])
async def list_templates(
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """List all email templates."""
    result = (
        db.table("email_templates")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return [EmailTemplateResponse(**t) for t in result.data]


@router.post("/templates", response_model=EmailTemplateResponse, status_code=201)
async def create_template(
    body: EmailTemplateCreate,
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Create a new email template."""
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        **body.model_dump(),
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }

    result = db.table("email_templates").insert(payload).execute()
    template = result.data[0]

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="create",
        resource="email_templates",
        resource_id=str(template["id"]),
        new_data=template,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="admin_create_email_template",
        metadata={"template_id": str(template["id"]), "slug": body.slug},
    )

    return EmailTemplateResponse(**template)


@router.put("/templates/{template_id}", response_model=EmailTemplateResponse)
async def update_template(
    template_id: str,
    body: EmailTemplateUpdate,
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Update an existing email template."""
    old_result = db.table("email_templates").select("*").eq("id", template_id).execute()
    if not old_result.data:
        raise not_found("Email template")
    old_template = old_result.data[0]

    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        return EmailTemplateResponse(**old_template)

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    result = (
        db.table("email_templates")
        .update(update_data)
        .eq("id", template_id)
        .execute()
    )
    template = result.data[0]

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="update",
        resource="email_templates",
        resource_id=template_id,
        old_data=old_template,
        new_data=template,
        ip=ip,
    )

    return EmailTemplateResponse(**template)


@router.delete("/templates/{template_id}", response_model=SuccessMessage)
async def deactivate_template(
    template_id: str,
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Deactivate an email template (soft delete)."""
    result = (
        db.table("email_templates")
        .update({"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", template_id)
        .execute()
    )
    if not result.data:
        raise not_found("Email template")

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="deactivate",
        resource="email_templates",
        resource_id=template_id,
        ip=ip,
    )

    return SuccessMessage(message="Email template deactivated.")


# ---------------------------------------------------------------------------
# Sequences
# ---------------------------------------------------------------------------


@router.get("/sequences", response_model=list[EmailSequenceResponse])
async def list_sequences(
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """List all email sequences."""
    result = (
        db.table("email_sequences")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return [EmailSequenceResponse(**s) for s in result.data]


@router.post("/sequences", response_model=EmailSequenceResponse, status_code=201)
async def create_sequence(
    body: EmailSequenceCreate,
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Create a new email sequence."""
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        **body.model_dump(),
        "created_at": now,
        "updated_at": now,
    }

    result = db.table("email_sequences").insert(payload).execute()
    sequence = result.data[0]

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="create",
        resource="email_sequences",
        resource_id=str(sequence["id"]),
        new_data=sequence,
        ip=ip,
    )
    await activity_service.track(
        db, user_id=user.id, action="admin_create_email_sequence",
        metadata={"sequence_id": str(sequence["id"]), "name": body.name},
    )

    return EmailSequenceResponse(**sequence)


@router.put("/sequences/{sequence_id}", response_model=EmailSequenceResponse)
async def update_sequence(
    sequence_id: str,
    body: EmailSequenceUpdate,
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Update an existing email sequence."""
    old_result = db.table("email_sequences").select("*").eq("id", sequence_id).execute()
    if not old_result.data:
        raise not_found("Email sequence")
    old_sequence = old_result.data[0]

    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        return EmailSequenceResponse(**old_sequence)

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    result = (
        db.table("email_sequences")
        .update(update_data)
        .eq("id", sequence_id)
        .execute()
    )
    sequence = result.data[0]

    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=user.id,
        action="update",
        resource="email_sequences",
        resource_id=sequence_id,
        old_data=old_sequence,
        new_data=sequence,
        ip=ip,
    )

    return EmailSequenceResponse(**sequence)


# ---------------------------------------------------------------------------
# Send history
# ---------------------------------------------------------------------------


@router.get("/sends")
async def list_sends(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    user_id: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """List email send history with filters."""
    offset = (page - 1) * per_page

    # Count query
    count_query = db.table("email_sends").select("id", count="exact")
    if user_id:
        count_query = count_query.eq("user_id", user_id)
    if status:
        count_query = count_query.eq("status", status)
    if date_from:
        count_query = count_query.gte("created_at", date_from)
    if date_to:
        count_query = count_query.lte("created_at", date_to)
    count_result = count_query.execute()
    total = count_result.count or 0

    # Data query
    data_query = db.table("email_sends").select("*")
    if user_id:
        data_query = data_query.eq("user_id", user_id)
    if status:
        data_query = data_query.eq("status", status)
    if date_from:
        data_query = data_query.gte("created_at", date_from)
    if date_to:
        data_query = data_query.lte("created_at", date_to)
    data_query = data_query.order("created_at", desc=True).range(offset, offset + per_page - 1)
    result = data_query.execute()

    return PaginatedResponse(
        data=result.data,
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
    )


# ---------------------------------------------------------------------------
# Test send
# ---------------------------------------------------------------------------


@router.post("/send-test", response_model=SuccessMessage)
async def send_test_email(
    request: Request,
    template_slug: str,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Send a test email using a template to the admin's own address."""
    await email_service.send_transactional(
        db,
        user_id=user.id,
        template_slug=template_slug,
        variables={"test": True, "admin_email": user.email},
    )

    await activity_service.track(
        db, user_id=user.id, action="admin_send_test_email",
        metadata={"template_slug": template_slug},
    )

    return SuccessMessage(message=f"Test email sent using template '{template_slug}'.")
