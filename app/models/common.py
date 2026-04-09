"""Common models, enums, and generic schemas used across the application."""

from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field


class Unit(str, Enum):
    """Measurement units for ingredients and supplies."""

    KG = "kg"
    G = "g"
    L = "L"
    ML = "ml"
    UN = "un"
    PCT = "pct"
    CX = "cx"


T = TypeVar("T")


class PaginationParams(BaseModel):
    """Query parameters for paginated endpoints."""

    page: int = Field(default=1, ge=1, description="Page number")
    per_page: int = Field(
        default=20, ge=1, le=100, description="Items per page"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{"page": 1, "per_page": 20}]
        }
    }


class PaginationMeta(BaseModel):
    """Metadata returned alongside paginated results."""

    page: int
    per_page: int
    total: int


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic wrapper for paginated list responses."""

    data: list[T]
    meta: PaginationMeta

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "data": [],
                    "meta": {"page": 1, "per_page": 20, "total": 0},
                }
            ]
        }
    }


class ErrorDetail(BaseModel):
    """Individual field-level error detail."""

    field: str = Field(..., description="Name of the field that caused the error")
    message: str = Field(..., description="Human-readable error message")


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    error: dict = Field(
        ...,
        description="Error object with code, message, and optional details",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Request validation failed",
                        "details": [
                            {
                                "field": "email",
                                "message": "Invalid email format",
                            }
                        ],
                    }
                }
            ]
        }
    }

    @staticmethod
    def create(
        code: str,
        message: str,
        details: list[ErrorDetail] | None = None,
    ) -> "ErrorResponse":
        """Factory helper to build a well-formed ErrorResponse."""
        return ErrorResponse(
            error={
                "code": code,
                "message": message,
                "details": [d.model_dump() for d in details] if details else [],
            }
        )


class SuccessMessage(BaseModel):
    """Simple success response with a message."""

    message: str = Field(..., description="Success message")

    model_config = {
        "json_schema_extra": {
            "examples": [{"message": "Operation completed successfully"}]
        }
    }
