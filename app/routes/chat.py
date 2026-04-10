from fastapi import APIRouter, Depends, Request, UploadFile, File, Form
from app.middleware.auth import get_current_user, UserContext
from app.database import get_supabase_client
from app.services import chat_service
from app.exceptions import AppException
from supabase import Client
from pydantic import BaseModel
import base64
import logging

logger = logging.getLogger("pizzacost.chat")

router = APIRouter(prefix="/api/v1", tags=["AI Features"])


class ChatRequest(BaseModel):
    message: str
    image_base64: str | None = None


class ShoppingListRequest(BaseModel):
    planned: list  # [{"flavor_id": "...", "quantity": 50}]
    name: str | None = None


class StockUpdateRequest(BaseModel):
    quantidade_estoque: float
    estoque_minimo: float | None = None


@router.post("/chat")
def send_chat(
    data: ChatRequest,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Send a chat message to the AI assistant."""
    response = chat_service.chat(db, user.id, data.message, data.image_base64)
    return {"data": {"message": response}}


@router.post("/chat/receipt")
def scan_receipt(
    data: ChatRequest,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Scan a receipt image and auto-update insumos."""
    if not data.image_base64:
        raise AppException("VALIDATION_ERROR", "Envie uma imagem da nota fiscal.", 400)
    result = chat_service.process_receipt(db, user.id, data.image_base64)
    return {"data": result}


@router.get("/chat/history")
def get_history(
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Get chat message history."""
    messages = db.table("chat_messages").select("role, content, created_at").eq("user_id", user.id).order("created_at", desc=True).limit(50).execute().data or []
    return {"data": list(reversed(messages))}


@router.delete("/chat/history")
def clear_history(
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Clear chat history."""
    db.table("chat_messages").delete().eq("user_id", user.id).execute()
    return {"data": {"message": "Historico limpo."}}


@router.get("/optimizer/analysis")
def get_menu_analysis(
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Run menu optimization analysis."""
    result = chat_service.analyze_menu(db, user.id)
    return {"data": result}


@router.put("/insumos/{insumo_id}/stock")
def update_stock(
    insumo_id: str,
    data: StockUpdateRequest,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Update stock for an insumo."""
    # Verify ownership
    insumo = db.table("insumos").select("id, quantidade_estoque").eq("id", insumo_id).eq("user_id", user.id).single().execute()
    if not insumo.data:
        raise AppException("NOT_FOUND", "Insumo nao encontrado.", 404)

    old_stock = insumo.data.get("quantidade_estoque", 0) or 0
    update_data = {"quantidade_estoque": data.quantidade_estoque, "ultima_atualizacao_estoque": "now()"}
    if data.estoque_minimo is not None:
        update_data["estoque_minimo"] = data.estoque_minimo

    db.table("insumos").update(update_data).eq("id", insumo_id).execute()

    # Log movement
    diff = data.quantidade_estoque - old_stock
    if diff != 0:
        db.table("stock_movements").insert({
            "user_id": user.id,
            "insumo_id": insumo_id,
            "tipo": "entrada" if diff > 0 else "saida",
            "quantidade": abs(diff),
            "observacao": "Ajuste manual"
        }).execute()

    return {"data": {"quantidade_estoque": data.quantidade_estoque}}


@router.get("/stock/overview")
def stock_overview(
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Get stock overview with alerts and capacity."""
    result = chat_service.get_stock_overview(db, user.id)
    return {"data": result}


@router.post("/shopping-list/generate")
def generate_shopping_list(
    data: ShoppingListRequest,
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """Generate a shopping list from planned production."""
    result = chat_service.generate_shopping_list(db, user.id, data.planned)

    # Save if name provided
    if data.name:
        db.table("shopping_lists").insert({
            "user_id": user.id,
            "name": data.name,
            "planned_production": data.planned,
            "items": result["items"],
            "total_estimated_cost": result["total_estimated_cost"]
        }).execute()

    return {"data": result}


@router.get("/shopping-lists")
def list_shopping_lists(
    user: UserContext = Depends(get_current_user),
    db: Client = Depends(get_supabase_client),
):
    """List saved shopping lists."""
    lists = db.table("shopping_lists").select("*").eq("user_id", user.id).order("created_at", desc=True).limit(20).execute().data or []
    return {"data": lists}
