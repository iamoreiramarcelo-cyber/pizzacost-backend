"""Borda (pizza crust/border) request/response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from .insumo import IngredienteItem


class BordaCreate(BaseModel):
    """Payload to create a new crust/border recipe."""

    nome: str = Field(
        ..., min_length=1, max_length=200, description="Border name"
    )
    tamanho_id: UUID = Field(
        ..., description="Pizza size this border applies to"
    )
    preco_venda: float | None = Field(
        default=None, ge=0, description="Selling price for this border option"
    )
    ingredientes: list[IngredienteItem] = Field(
        ..., min_length=1, description="Ingredients that make up the border"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "nome": "Catupiry",
                    "tamanho_id": "c3d4e5f6-7890-4abc-9def-1234567890ab",
                    "preco_venda": 8.00,
                    "ingredientes": [
                        {
                            "insumo_id": "a1b2c3d4-5678-4abc-9def-1234567890ab",
                            "quantidade": 0.15,
                            "unidade": "kg",
                        }
                    ],
                }
            ]
        }
    }


class BordaUpdate(BaseModel):
    """Partial update for an existing border. All fields optional."""

    nome: str | None = Field(
        default=None, min_length=1, max_length=200, description="Border name"
    )
    tamanho_id: UUID | None = Field(
        default=None, description="Pizza size ID"
    )
    preco_venda: float | None = Field(
        default=None, ge=0, description="Selling price"
    )
    ingredientes: list[IngredienteItem] | None = Field(
        default=None, min_length=1, description="Ingredients list"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "preco_venda": 10.00,
                }
            ]
        }
    }


class BordaResponse(BaseModel):
    """Border/crust as returned by the API."""

    id: UUID
    user_id: UUID
    nome: str
    tamanho_id: UUID
    preco_venda: float | None = None
    ingredientes: list[dict] = Field(
        default_factory=list,
        description="Ingredient breakdown with resolved names and costs",
    )
    custo_calculado: float = Field(
        ..., description="Total computed cost of the border"
    )
    created_at: datetime
    updated_at: datetime

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "d4e5f6a7-8901-4abc-9def-1234567890ab",
                    "user_id": "b5f7c2a0-1234-4abc-9def-1234567890ab",
                    "nome": "Catupiry",
                    "tamanho_id": "c3d4e5f6-7890-4abc-9def-1234567890ab",
                    "preco_venda": 8.00,
                    "ingredientes": [
                        {
                            "insumo_id": "a1b2c3d4-5678-4abc-9def-1234567890ab",
                            "nome": "Catupiry",
                            "quantidade": 0.15,
                            "unidade": "kg",
                            "custo": 6.44,
                        }
                    ],
                    "custo_calculado": 6.44,
                    "created_at": "2025-06-01T12:00:00Z",
                    "updated_at": "2025-06-01T12:00:00Z",
                }
            ]
        }
    }
