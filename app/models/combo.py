"""Combo (pizza bundle) request/response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ComboPizzaItem(BaseModel):
    """A pizza entry inside a combo."""

    flavor_id: UUID = Field(..., description="Pizza recipe ID")
    quantidade: int = Field(..., gt=0, description="Number of this flavor in the combo")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "flavor_id": "e5f6a7b8-9012-4abc-9def-1234567890ab",
                    "quantidade": 2,
                }
            ]
        }
    }


class ComboCreate(BaseModel):
    """Payload to create a new combo/bundle."""

    nome: str = Field(
        ..., min_length=1, max_length=200, description="Combo name"
    )
    pizzas: list[ComboPizzaItem] = Field(
        ..., min_length=1, description="Pizzas included in the combo"
    )
    outros_custos: float = Field(
        default=0, ge=0, description="Additional costs (drinks, sides, etc.)"
    )
    preco_venda_sugerido: float = Field(
        ..., ge=0, description="Suggested selling price for the combo"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "nome": "Combo Familia",
                    "pizzas": [
                        {
                            "flavor_id": "e5f6a7b8-9012-4abc-9def-1234567890ab",
                            "quantidade": 2,
                        },
                        {
                            "flavor_id": "f6a7b8c9-0123-4abc-9def-1234567890ab",
                            "quantidade": 1,
                        },
                    ],
                    "outros_custos": 5.00,
                    "preco_venda_sugerido": 120.00,
                }
            ]
        }
    }


class ComboUpdate(BaseModel):
    """Partial update for an existing combo. All fields optional."""

    nome: str | None = Field(
        default=None, min_length=1, max_length=200, description="Combo name"
    )
    pizzas: list[ComboPizzaItem] | None = Field(
        default=None, min_length=1, description="Pizzas in the combo"
    )
    outros_custos: float | None = Field(
        default=None, ge=0, description="Additional costs"
    )
    preco_venda_sugerido: float | None = Field(
        default=None, ge=0, description="Suggested selling price"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "preco_venda_sugerido": 115.00,
                }
            ]
        }
    }


class ComboResponse(BaseModel):
    """Combo as returned by the API."""

    id: UUID
    user_id: UUID
    nome: str
    pizzas: list[dict] = Field(
        default_factory=list,
        description="Pizza entries with resolved names and costs",
    )
    outros_custos: float
    preco_venda_sugerido: float
    custo_calculado: float = Field(
        ..., description="Total computed cost of all pizzas + other costs"
    )
    margem_lucro: float | None = Field(
        default=None,
        description="Profit margin percentage",
    )
    created_at: datetime
    updated_at: datetime

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "a7b8c9d0-1234-4abc-9def-1234567890ab",
                    "user_id": "b5f7c2a0-1234-4abc-9def-1234567890ab",
                    "nome": "Combo Familia",
                    "pizzas": [
                        {
                            "flavor_id": "e5f6a7b8-9012-4abc-9def-1234567890ab",
                            "nome": "Margherita",
                            "quantidade": 2,
                            "custo_unitario": 17.23,
                        }
                    ],
                    "outros_custos": 5.00,
                    "preco_venda_sugerido": 120.00,
                    "custo_calculado": 39.46,
                    "margem_lucro": 67.12,
                    "created_at": "2025-06-01T12:00:00Z",
                    "updated_at": "2025-06-01T12:00:00Z",
                }
            ]
        }
    }
