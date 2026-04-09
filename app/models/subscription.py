"""Subscription and plan-limit schemas."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SubscriptionStatus(str, Enum):
    """Available subscription tiers."""

    FREE = "free"
    PAID = "paid"


class PlanLimits(BaseModel):
    """Resource limits for the current subscription plan."""

    tamanhos: int = Field(..., description="Max pizza sizes allowed")
    bordas: int = Field(..., description="Max borders allowed")
    pizzas: int = Field(..., description="Max pizza recipes allowed")
    combos: int = Field(..., description="Max combos allowed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "tamanhos": 3,
                    "bordas": 5,
                    "pizzas": 10,
                    "combos": 5,
                }
            ]
        }
    }


class SubscriptionResponse(BaseModel):
    """Current subscription state for the authenticated user."""

    status: SubscriptionStatus
    expires_at: datetime | None = Field(
        default=None, description="Expiration date (None for free tier)"
    )
    limits: PlanLimits

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "paid",
                    "expires_at": "2026-06-01T00:00:00Z",
                    "limits": {
                        "tamanhos": 50,
                        "bordas": 100,
                        "pizzas": 200,
                        "combos": 50,
                    },
                }
            ]
        }
    }


class SubscriptionActivateRequest(BaseModel):
    """Admin-initiated manual subscription activation."""

    payment_id: str = Field(
        ..., description="External payment/transaction ID for audit trail"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{"payment_id": "pay_abc123xyz"}]
        }
    }
