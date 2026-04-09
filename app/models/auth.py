"""Authentication request/response schemas."""

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Credentials for user login."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="User password")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "email": "usuario@exemplo.com",
                    "password": "senhaSegura123",
                }
            ]
        }
    }


class SignupRequest(BaseModel):
    """Payload for new user registration."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (8-128 characters)",
    )
    nome_loja: str = Field(
        ..., max_length=200, description="Store / business name"
    )
    telefone: str | None = Field(
        default=None, max_length=20, description="Phone number"
    )
    marketing_opt_in: bool = Field(
        default=False,
        description="Whether the user opts in to marketing communications",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "email": "novousuario@exemplo.com",
                    "password": "SenhaForte!2024",
                    "nome_loja": "Pizzaria do Marcelo",
                    "telefone": "+5511999998888",
                    "marketing_opt_in": True,
                }
            ]
        }
    }


class TokenResponse(BaseModel):
    """JWT token pair returned after successful authentication."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(
        ..., description="Token lifetime in seconds"
    )
    user: dict = Field(
        ..., description="Basic user info (id, email, role)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "access_token": "eyJhbGciOiJIUzI1NiIs...",
                    "token_type": "bearer",
                    "expires_in": 3600,
                    "user": {
                        "id": "b5f7c2a0-1234-4abc-9def-1234567890ab",
                        "email": "usuario@exemplo.com",
                        "role": "user",
                    },
                }
            ]
        }
    }


class PasswordResetRequest(BaseModel):
    """Request a password-reset email."""

    email: EmailStr = Field(..., description="Email linked to the account")

    model_config = {
        "json_schema_extra": {
            "examples": [{"email": "usuario@exemplo.com"}]
        }
    }


class PasswordResetConfirm(BaseModel):
    """Confirm a password reset with the token received via email."""

    token: str = Field(..., description="Password-reset token")
    new_password: str = Field(
        ..., min_length=8, description="New password (min 8 characters)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "token": "abc123resettoken",
                    "new_password": "NovaSenhaForte!2024",
                }
            ]
        }
    }
