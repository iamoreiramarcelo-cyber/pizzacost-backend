"""Pizza request/response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from .insumo import IngredienteItem


class PizzaCreate(BaseModel):
    """Payload to create a new pizza recipe."""

    nome: str = Field(
        ..., min_length=1, max_length=200, description="Pizza flavor name"
    )
    tamanho_id: UUID = Field(..., description="Pizza size reference")
    border_id: UUID | None = Field(
        default=None, description="Optional border/crust reference"
    )
    ingredientes: list[IngredienteItem] = Field(
        ..., min_length=1, description="Topping / filling ingredients"
    )
    custo_adicionais: float = Field(
        default=0, ge=0, description="Extra costs (gas, labor, etc.)"
    )
    preco_venda: float | None = Field(
        default=None, ge=0, description="Desired selling price"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "nome": "Margherita",
                    "tamanho_id": "c3d4e5f6-7890-4abc-9def-1234567890ab",
                    "border_id": None,
                    "ingredientes": [
                        {
                            "insumo_id": "a1b2c3d4-5678-4abc-9def-1234567890ab",
                            "quantidade": 0.25,
                            "unidade": "kg",
                        },
                        {
                            "insumo_id": "b2c3d4e5-6789-4abc-9def-1234567890ab",
                            "quantidade": 0.1,
                            "unidade": "kg",
                        },
                    ],
                    "custo_adicionais": 1.50,
                    "preco_venda": 45.00,
                }
            ]
        }
    }


class PizzaUpdate(BaseModel):
    """Partial update for an existing pizza. All fields optional."""

    nome: str | None = Field(
        default=None, min_length=1, max_length=200, description="Pizza name"
    )
    tamanho_id: UUID | None = Field(
        default=None, description="Pizza size reference"
    )
    border_id: UUID | None = Field(
        default=None, description="Border/crust reference"
    )
    ingredientes: list[IngredienteItem] | None = Field(
        default=None, min_length=1, description="Ingredients list"
    )
    custo_adicionais: float | None = Field(
        default=None, ge=0, description="Extra costs"
    )
    preco_venda: float | None = Field(
        default=None, ge=0, description="Selling price"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "preco_venda": 48.00,
                }
            ]
        }
    }


class PizzaResponse(BaseModel):
    """Pizza recipe as returned by the API."""

    id: UUID
    user_id: UUID
    nome: str
    tamanho_id: UUID
    border_id: UUID | None = None
    ingredientes: list[dict] = Field(
        default_factory=list,
        description="Ingredient breakdown with resolved names and costs",
    )
    custo_adicionais: float
    preco_venda: float | None = None
    custo_calculado: float = Field(
        ..., description="Total computed cost (ingredients + dough + packaging + border + extras)"
    )
    margem_lucro: float | None = Field(
        default=None,
        description="Profit margin percentage ((preco_venda - custo_calculado) / preco_venda * 100)",
    )
    created_at: datetime
    updated_at: datetime

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "e5f6a7b8-9012-4abc-9def-1234567890ab",
                    "user_id": "b5f7c2a0-1234-4abc-9def-1234567890ab",
                    "nome": "Margherita",
                    "tamanho_id": "c3d4e5f6-7890-4abc-9def-1234567890ab",
                    "border_id": None,
                    "ingredientes": [
                        {
                            "insumo_id": "a1b2c3d4-5678-4abc-9def-1234567890ab",
                            "nome": "Mussarela",
                            "quantidade": 0.25,
                            "unidade": "kg",
                            "custo": 10.73,
                        }
                    ],
                    "custo_adicionais": 1.50,
                    "preco_venda": 45.00,
                    "custo_calculado": 17.23,
                    "margem_lucro": 61.71,
                    "created_at": "2025-06-01T12:00:00Z",
                    "updated_at": "2025-06-01T12:00:00Z",
                }
            ]
        }
    }
