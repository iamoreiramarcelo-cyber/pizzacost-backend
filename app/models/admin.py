"""Admin-only request/response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class AdminUserCreate(BaseModel):
    """Admin payload to create a new user manually."""

    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=8, description="Initial password")
    nome_loja: str = Field(..., max_length=200, description="Store name")
    telefone: str | None = Field(
        default=None, max_length=20, description="Phone number"
    )
    role: str = Field(
        default="user", description="User role (user / admin)"
    )
    subscription_status: str = Field(
        default="free", description="Initial subscription status (free / paid)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "email": "novo@exemplo.com",
                    "password": "SenhaInicial!2024",
                    "nome_loja": "Pizzaria Nova",
                    "telefone": "+5511988887777",
                    "role": "user",
                    "subscription_status": "free",
                }
            ]
        }
    }


class AdminUserUpdate(BaseModel):
    """Admin payload to update any user. All fields optional."""

    nome_loja: str | None = Field(
        default=None, max_length=200, description="Store name"
    )
    telefone: str | None = Field(
        default=None, max_length=20, description="Phone number"
    )
    role: str | None = Field(default=None, description="User role")
    subscription_status: str | None = Field(
        default=None, description="Subscription status"
    )
    is_active: bool | None = Field(
        default=None, description="Whether the account is active"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "subscription_status": "paid",
                    "is_active": True,
                }
            ]
        }
    }


class AdminDashboardResponse(BaseModel):
    """Aggregate metrics shown on the admin dashboard."""

    total_users: int = Field(..., description="Total registered users")
    paid_users: int = Field(..., description="Users with active paid subscription")
    free_users: int = Field(..., description="Users on the free tier")
    mrr: float = Field(..., description="Monthly Recurring Revenue (BRL)")
    churn_rate: float = Field(
        ..., description="Churn rate percentage over the last 30 days"
    )
    new_signups_30d: int = Field(
        ..., description="New registrations in the last 30 days"
    )
    revenue_30d: float = Field(
        ..., description="Total revenue in the last 30 days (BRL)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "total_users": 1250,
                    "paid_users": 320,
                    "free_users": 930,
                    "mrr": 9600.00,
                    "churn_rate": 3.2,
                    "new_signups_30d": 85,
                    "revenue_30d": 9600.00,
                }
            ]
        }
    }


class AdminUserListItem(BaseModel):
    """Compact user record for admin user listings."""

    id: UUID
    email: str
    nome_loja: str | None = None
    telefone: str | None = None
    role: str
    subscription_status: str
    created_at: datetime
    last_activity: datetime | None = None


class LgpdRequestResponse(BaseModel):
    """LGPD (data privacy) request record."""

    id: UUID
    user_id: UUID
    user_email: str
    request_type: str = Field(
        ..., description="Type of LGPD request (export / deletion / rectification)"
    )
    status: str = Field(
        ..., description="Processing status (pending / processing / completed / rejected)"
    )
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "f1a2b3c4-5678-4abc-9def-1234567890ab",
                    "user_id": "b5f7c2a0-1234-4abc-9def-1234567890ab",
                    "user_email": "usuario@exemplo.com",
                    "request_type": "export",
                    "status": "completed",
                    "created_at": "2025-06-01T12:00:00Z",
                    "completed_at": "2025-06-02T08:00:00Z",
                }
            ]
        }
    }


class AuditLogResponse(BaseModel):
    """Single audit-log entry."""

    id: UUID
    user_id: UUID | None = None
    user_email: str | None = None
    action: str = Field(..., description="Action performed (create / update / delete / login / etc.)")
    resource: str = Field(..., description="Resource type (user / insumo / pizza / etc.)")
    resource_id: str | None = Field(
        default=None, description="ID of the affected resource"
    )
    ip_address: str | None = Field(
        default=None, description="Client IP address"
    )
    created_at: datetime

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "a0b1c2d3-4567-4abc-9def-1234567890ab",
                    "user_id": "b5f7c2a0-1234-4abc-9def-1234567890ab",
                    "user_email": "admin@exemplo.com",
                    "action": "update",
                    "resource": "user",
                    "resource_id": "c3d4e5f6-7890-4abc-9def-1234567890ab",
                    "ip_address": "189.10.20.30",
                    "created_at": "2025-06-01T14:30:00Z",
                }
            ]
        }
    }


class AdminSettingsUpdate(BaseModel):
    """Update a single system setting by key (key comes from URL path)."""

    value: dict = Field(..., description="Setting value as a JSON object")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "value": {
                        "tamanhos": 3,
                        "bordas": 5,
                        "pizzas": 10,
                        "combos": 5,
                    },
                }
            ]
        }
    }
