"""Admin reporting routes for PizzaCost Pro."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.database import get_supabase_client
from app.middleware.auth import require_admin, UserContext
from app.models import AdminDashboardResponse
from app.services import admin_service

router = APIRouter(prefix="/api/v1/admin/reports", tags=["Admin - Reports"])


@router.get("/dashboard", response_model=AdminDashboardResponse)
async def get_admin_dashboard(
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Get the admin dashboard with total users, MRR, churn, etc."""
    data = await admin_service.get_dashboard(db)

    # Add revenue_30d (same as mrr for monthly billing)
    return AdminDashboardResponse(
        total_users=data["total_users"],
        paid_users=data["paid_users"],
        free_users=data["free_users"],
        mrr=data["mrr"],
        churn_rate=data["churn_rate"],
        new_signups_30d=data["new_signups_30d"],
        revenue_30d=data["mrr"],
    )


@router.get("/revenue")
async def get_revenue_report(
    request: Request,
    date_from: str | None = None,
    date_to: str | None = None,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Revenue report with date range filter.

    Returns payment logs aggregated by status within the specified period.
    """
    if not date_from:
        date_from = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    if not date_to:
        date_to = datetime.now(timezone.utc).isoformat()

    # Fetch payment logs within date range
    result = (
        db.table("payment_logs")
        .select("*")
        .gte("created_at", date_from)
        .lte("created_at", date_to)
        .order("created_at", desc=True)
        .execute()
    )
    payments = result.data

    # Aggregate
    total_revenue = sum(
        float(p.get("amount_brl", 0)) for p in payments if p.get("status") == "approved"
    )
    total_transactions = len(payments)
    approved_count = sum(1 for p in payments if p.get("status") == "approved")
    rejected_count = sum(1 for p in payments if p.get("status") == "rejected")
    refunded_count = sum(1 for p in payments if p.get("status") == "refunded")
    pending_count = sum(1 for p in payments if p.get("status") == "pending")

    return {
        "date_from": date_from,
        "date_to": date_to,
        "total_revenue": round(total_revenue, 2),
        "total_transactions": total_transactions,
        "approved": approved_count,
        "rejected": rejected_count,
        "refunded": refunded_count,
        "pending": pending_count,
        "payments": payments,
    }


@router.get("/churn")
async def get_churn_analysis(
    request: Request,
    date_from: str | None = None,
    date_to: str | None = None,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Churn analysis report.

    Analyzes subscription history to identify churn patterns.
    """
    if not date_from:
        date_from = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    if not date_to:
        date_to = datetime.now(timezone.utc).isoformat()

    # Fetch subscription changes in period
    history_result = (
        db.table("subscription_history")
        .select("*")
        .gte("created_at", date_from)
        .lte("created_at", date_to)
        .order("created_at", desc=True)
        .execute()
    )
    history = history_result.data

    # Churned users (moved from paid to free)
    churned = [h for h in history if h.get("new_status") == "free" and h.get("old_status") == "paid"]
    # Activated users (moved from free to paid)
    activated = [h for h in history if h.get("new_status") == "paid" and h.get("old_status") == "free"]

    # Current paid users for churn rate calculation
    paid_result = (
        db.table("profiles")
        .select("id", count="exact")
        .eq("subscription_status", "paid")
        .execute()
    )
    current_paid = paid_result.count or 0
    paid_at_start = current_paid + len(churned)
    churn_rate = round((len(churned) / paid_at_start * 100), 2) if paid_at_start > 0 else 0.0

    # Churn reasons
    reasons: dict[str, int] = {}
    for entry in churned:
        reason = entry.get("reason", "unknown")
        reasons[reason] = reasons.get(reason, 0) + 1

    return {
        "date_from": date_from,
        "date_to": date_to,
        "total_churned": len(churned),
        "total_activated": len(activated),
        "net_change": len(activated) - len(churned),
        "churn_rate_percent": churn_rate,
        "current_paid_users": current_paid,
        "churn_reasons": reasons,
        "churned_details": churned,
        "activated_details": activated,
    }
