"""Admin reporting routes for PizzaCost Pro."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.database import get_supabase_client
from app.middleware.auth import require_admin, UserContext
from app.models import AdminDashboardResponse
from app.services import admin_service

router = APIRouter(prefix="/api/v1/admin/reports", tags=["Admin - Reports"])


@router.get("/dashboard")
async def get_admin_dashboard(
    request: Request,
    user: UserContext = Depends(require_admin),
    db: Client = Depends(get_supabase_client),
):
    """Get the full admin dashboard with KPIs, funnel, health, top stores, tags."""
    data = await admin_service.get_dashboard(db)

    # Fetch all profiles for detailed stats
    all_profiles = db.table("profiles").select("id, email, nome_loja, subscription_status, tag, created_at, deleted_at").is_("deleted_at", "null").execute().data or []

    total = len(all_profiles)
    paid = sum(1 for p in all_profiles if p.get("subscription_status") == "paid")
    free = total - paid

    # Tags
    tags = {"nao_assinante": 0, "assinante": 0, "aquecido": 0}
    for p in all_profiles:
        t = p.get("tag", "nao_assinante") or "nao_assinante"
        if t in tags:
            tags[t] += 1

    # Health score (based on user_activity)
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    d7 = (now - timedelta(days=7)).isoformat()
    d14 = (now - timedelta(days=14)).isoformat()

    recent_activity = db.table("user_activity").select("user_id, created_at").gte("created_at", d14).execute().data or []
    active_7d = set()
    active_14d = set()
    for a in recent_activity:
        uid = a.get("user_id")
        if a.get("created_at", "") >= d7:
            active_7d.add(uid)
        active_14d.add(uid)

    healthy = len(active_7d)
    at_risk = len(active_14d - active_7d)
    inactive = total - len(active_14d)

    # Top pizzarias (by number of pizzas/sabores)
    top_stores = []
    for p in all_profiles[:50]:  # Check first 50
        sabores_count = db.table("pizzas").select("id", count="exact").eq("user_id", p["id"]).execute().count or 0
        if sabores_count > 0:
            top_stores.append({
                "nome_loja": p.get("nome_loja") or p.get("email", "").split("@")[0],
                "sabores": sabores_count,
                "ultimo_acesso": p.get("created_at", "")[:10]
            })
    top_stores.sort(key=lambda x: x["sabores"], reverse=True)

    # Funnel: signup -> has insumo -> has sabor -> has preco_venda -> is paid
    users_with_insumo = set()
    users_with_sabor = set()
    for p in all_profiles:
        uid = p["id"]
        ic = db.table("insumos").select("id", count="exact").eq("user_id", uid).execute().count or 0
        if ic > 0:
            users_with_insumo.add(uid)
            pc = db.table("pizzas").select("id", count="exact").eq("user_id", uid).execute().count or 0
            if pc > 0:
                users_with_sabor.add(uid)

    funnel = [
        {"label": "Signup", "value": total, "total": total},
        {"label": "1o Insumo", "value": len(users_with_insumo), "total": total},
        {"label": "1o Sabor", "value": len(users_with_sabor), "total": total},
        {"label": "Upgrade", "value": paid, "total": total},
    ]

    # Pending actions
    pending = []
    failed_payments = db.table("payment_logs").select("id", count="exact").eq("status", "rejected").execute().count or 0
    if failed_payments > 0:
        pending.append({"type": "payment", "label": "Pagamentos falhados", "count": failed_payments})
    new_tickets = db.table("support_tickets").select("id", count="exact").eq("status", "novo").execute().count or 0
    if new_tickets > 0:
        pending.append({"type": "ticket", "label": "Tickets novos", "count": new_tickets})

    return {
        "total_users": total,
        "paid_users": paid,
        "free_users": free,
        "mrr": data["mrr"],
        "churn_rate": data["churn_rate"],
        "new_signups_30d": data["new_signups_30d"],
        "revenue_30d": data["mrr"],
        "tags": tags,
        "health": {"healthy": healthy, "atRisk": at_risk, "inactive": inactive},
        "funnel": funnel,
        "topPizzarias": top_stores[:5],
        "pendingActions": pending,
    }


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
