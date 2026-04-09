"""Insumo (supply/ingredient) request/response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from .common import Unit


class IngredienteItem(BaseModel):
    """A single ingredient line used inside recipes (pizzas, bordas, etc.)."""

    insumo_id: UUID = Field(..., description="ID of the supply/ingredient")
    quantidade: float = Field(..., gt=0, description="Amount used")
    unidade: Unit | None = Field(
        default=None,
        description="Override unit; if omitted, the insumo's default unit is used",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "insumo_id": "a1b2c3d4-5678-4abc-9def-1234567890ab",
                    "quantidade": 0.3,
                    "unidade": "kg",
                }
            ]
        }
    }


class InsumoCreate(BaseModel):
    """Payload to create a new supply item."""

    nome: str = Field(
        ..., min_length=1, max_length=200, description="Supply name"
    )
    unidade: Unit = Field(..., description="Measurement unit")
    preco: float = Field(..., gt=0, description="Purchase price")
    quantidade_comprada: float = Field(
        ..., gt=0, description="Quantity purchased for the given price"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "nome": "Mussarela",
                    "unidade": "kg",
                    "preco": 42.90,
                    "quantidade_comprada": 1.0,
                }
            ]
        }
    }


class InsumoUpdate(BaseModel):
    """Partial update for an existing supply item. All fields optional."""

    nome: str | None = Field(
        default=None, min_length=1, max_length=200, description="Supply name"
    )
    unidade: Unit | None = Field(
        default=None, description="Measurement unit"
    )
    preco: float | None = Field(
        default=None, gt=0, description="Purchase price"
    )
    quantidade_comprada: float | None = Field(
        default=None, gt=0, description="Quantity purchased"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "preco": 45.50,
                    "quantidade_comprada": 1.0,
                }
            ]
        }
    }


class InsumoResponse(BaseModel):
    """Supply item as returned by the API."""

    id: UUID
    user_id: UUID
    nome: str
    unidade: str
    preco: float
    quantidade_comprada: float
    custo_unitario: float = Field(
        ..., description="Computed unit cost (preco / quantidade_comprada)"
    )
    created_at: datetime
    updated_at: datetime

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "a1b2c3d4-5678-4abc-9def-1234567890ab",
                    "user_id": "b5f7c2a0-1234-4abc-9def-1234567890ab",
                    "nome": "Mussarela",
                    "unidade": "kg",
                    "preco": 42.90,
                    "quantidade_comprada": 1.0,
                    "custo_unitario": 42.90,
                    "created_at": "2025-06-01T12:00:00Z",
                    "updated_at": "2025-06-01T12:00:00Z",
                }
            ]
        }
    }
