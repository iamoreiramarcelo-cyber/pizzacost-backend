"""User profile request/response schemas."""

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ProfileResponse(BaseModel):
    """Full user profile returned by the API."""

    id: UUID
    email: str
    nome_loja: str | None = None
    telefone: str | None = None
    subscription_status: str = Field(
        ..., description="Current subscription status (free / paid)"
    )
    role: str = Field(..., description="User role (user / admin)")
    created_at: datetime
    subscription_expires_at: datetime | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "b5f7c2a0-1234-4abc-9def-1234567890ab",
                    "email": "usuario@exemplo.com",
                    "nome_loja": "Pizzaria do Marcelo",
                    "telefone": "+5511999998888",
                    "subscription_status": "paid",
                    "role": "user",
                    "created_at": "2025-01-15T10:30:00Z",
                    "subscription_expires_at": "2026-01-15T10:30:00Z",
                }
            ]
        }
    }


class ProfileUpdate(BaseModel):
    """Partial update for the authenticated user's profile."""

    nome_loja: str | None = Field(
        default=None, max_length=200, description="Store name"
    )
    telefone: str | None = Field(
        default=None, max_length=20, description="Phone number"
    )

    @field_validator("telefone")
    @classmethod
    def validate_telefone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # Accept digits, spaces, dashes, parentheses, and leading +
        pattern = r"^\+?[\d\s\-()]{7,20}$"
        if not re.match(pattern, v):
            raise ValueError(
                "Invalid phone format. Use digits, spaces, dashes, "
                "parentheses, and an optional leading '+'."
            )
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "nome_loja": "Pizzaria Renovada",
                    "telefone": "+5511999997777",
                }
            ]
        }
    }
