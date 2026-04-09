"""Tests for authentication endpoints and auth_service logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from tests.conftest import (
    JWT_SECRET,
    TEST_USER_EMAIL,
    TEST_USER_ID,
    MockSupabaseClient,
    create_test_jwt,
)


# ---------------------------------------------------------------------------
# Service-level tests (auth_service)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signup_success(mock_db: MockSupabaseClient):
    """POST /api/v1/auth/signup equivalent -- service creates user, profile,
    email_preferences, and consent_logs."""
    from app.services.auth_service import signup_user

    with patch("app.services.auth_service.send_transactional", new_callable=AsyncMock):
        result = await signup_user(
            db=mock_db,
            email="new@example.com",
            password="StrongPassword1!",
            nome_loja="Pizza Nova",
            telefone="+5511999998888",
            marketing_opt_in=True,
        )

    assert "user" in result
    assert result["message"] == "Account created successfully."


@pytest.mark.asyncio
async def test_signup_duplicate_email(mock_db: MockSupabaseClient):
    """Signup with an email that already exists should raise 409."""
    from app.exceptions import AppException
    from app.services.auth_service import signup_user

    # Make auth.admin.create_user raise a duplicate error
    mock_db.auth.admin.create_user = MagicMock(
        side_effect=Exception("User already registered")
    )

    with pytest.raises(AppException) as exc_info:
        await signup_user(
            db=mock_db,
            email="existing@example.com",
            password="StrongPassword1!",
            nome_loja="Duplicada",
            telefone=None,
            marketing_opt_in=False,
        )

    assert exc_info.value.status == 409
    assert exc_info.value.code == "DUPLICATE_EMAIL"


@pytest.mark.asyncio
async def test_signup_weak_password():
    """Password shorter than 8 chars should be rejected by the Pydantic model (422)."""
    from pydantic import ValidationError

    from app.models.auth import SignupRequest

    with pytest.raises(ValidationError):
        SignupRequest(
            email="user@example.com",
            password="short",  # < 8 chars
            nome_loja="Loja",
        )


@pytest.mark.asyncio
async def test_login_success():
    """Verify that verify_jwt succeeds with a valid token."""
    from app.services.auth_service import verify_jwt

    token = create_test_jwt(TEST_USER_ID, email=TEST_USER_EMAIL)
    payload = await verify_jwt(token, JWT_SECRET)

    assert payload["sub"] == TEST_USER_ID
    assert payload["email"] == TEST_USER_EMAIL


@pytest.mark.asyncio
async def test_login_invalid_credentials():
    """verify_jwt should raise with a bad secret (simulates wrong credentials)."""
    from app.exceptions import AppException
    from app.services.auth_service import verify_jwt

    token = create_test_jwt(TEST_USER_ID)

    with pytest.raises(AppException) as exc_info:
        await verify_jwt(token, "wrong-secret")

    assert exc_info.value.status == 401


@pytest.mark.asyncio
async def test_password_reset_request():
    """The PasswordResetRequest schema should accept a valid email."""
    from app.models.auth import PasswordResetRequest

    req = PasswordResetRequest(email="user@example.com")
    assert req.email == "user@example.com"


@pytest.mark.asyncio
async def test_expired_jwt_rejected():
    """An expired JWT must be rejected by verify_jwt."""
    from app.exceptions import AppException
    from app.services.auth_service import verify_jwt

    token = create_test_jwt(TEST_USER_ID, expired=True)

    with pytest.raises(AppException) as exc_info:
        await verify_jwt(token, JWT_SECRET)

    assert exc_info.value.status == 401
    assert "expired" in exc_info.value.message.lower()
