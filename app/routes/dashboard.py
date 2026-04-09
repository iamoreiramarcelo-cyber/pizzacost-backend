"""User dashboard routes for PizzaCost Pro."""

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.database import get_supabase_client
from app.middleware.auth import get_current_user, UserContext
from app.services import dashboard_service

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


@router.get("/")
async def get_dashboard(
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Get the user's dashboard data including counts, top pizzas, and top combos."""
    data = await dashboard_service.get_user_dashboard(db, user_id=user.id)
    return data
