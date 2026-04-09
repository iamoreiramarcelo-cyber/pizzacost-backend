"""Tamanho (pizza size) request/response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TamanhoCreate(BaseModel):
    """Payload to create a new pizza size."""

    nome: str = Field(
        ..., min_length=1, max_length=200, description="Size name (e.g. Grande, Media)"
    )
    preco_total: float = Field(
        ..., ge=0, description="Total packaging price for this size"
    )
    quantidade_embalagens: int = Field(
        ..., gt=0, description="Number of packaging units included in the price"
    )
    custo_massa: float = Field(
        ..., ge=0, description="Dough cost for this pizza size"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "nome": "Grande",
                    "preco_total": 15.00,
                    "quantidade_embalagens": 10,
                    "custo_massa": 3.50,
                }
            ]
        }
    }


class TamanhoUpdate(BaseModel):
    """Partial update for an existing pizza size. All fields optional."""

    nome: str | None = Field(
        default=None, min_length=1, max_length=200, description="Size name"
    )
    preco_total: float | None = Field(
        default=None, ge=0, description="Total packaging price"
    )
    quantidade_embalagens: int | None = Field(
        default=None, gt=0, description="Number of packaging units"
    )
    custo_massa: float | None = Field(
        default=None, ge=0, description="Dough cost"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "custo_massa": 4.00,
                }
            ]
        }
    }


class TamanhoResponse(BaseModel):
    """Pizza size as returned by the API."""

    id: UUID
    user_id: UUID
    nome: str
    custo_embalagem: float = Field(
        ..., description="Computed per-unit packaging cost"
    )
    custo_massa: float
    preco_total: float
    quantidade_embalagens: int
    created_at: datetime
    updated_at: datetime

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "c3d4e5f6-7890-4abc-9def-1234567890ab",
                    "user_id": "b5f7c2a0-1234-4abc-9def-1234567890ab",
                    "nome": "Grande",
                    "custo_embalagem": 1.50,
                    "custo_massa": 3.50,
                    "preco_total": 15.00,
                    "quantidade_embalagens": 10,
                    "created_at": "2025-06-01T12:00:00Z",
                    "updated_at": "2025-06-01T12:00:00Z",
                }
            ]
        }
    }
