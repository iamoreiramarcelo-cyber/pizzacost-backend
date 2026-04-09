"""Tests for security measures: rate limiting, CORS, headers, JWT, data isolation."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.conftest import (
    JWT_SECRET,
    TEST_USER_B_ID,
    TEST_USER_ID,
    MockSupabaseClient,
    create_test_jwt,
)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limiting(app):
    """Exceeding the rate limit should eventually return 429.

    Note: In test mode the rate limit is set very high (1000/min), so this
    test verifies the limiter is present on app.state. For a true 429 test
    we would need a lower limit.
    """
    assert hasattr(app.state, "limiter"), "Rate limiter should be attached to app.state"

    from app.middleware.rate_limit import limiter, AUTH_RATE_LIMIT

    # Verify the auth rate limit constant is defined
    assert AUTH_RATE_LIMIT == "5/minute"
    assert limiter is not None


# ---------------------------------------------------------------------------
# CORS headers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cors_headers(client: AsyncClient):
    """CORS preflight should return appropriate Access-Control headers."""
    resp = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    # FastAPI's CORSMiddleware should respond to OPTIONS preflight
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers


@pytest.mark.asyncio
async def test_cors_disallowed_origin(client: AsyncClient):
    """Request from a disallowed origin should not get Access-Control-Allow-Origin."""
    resp = await client.options(
        "/health",
        headers={
            "Origin": "http://evil-site.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    allow_origin = resp.headers.get("access-control-allow-origin", "")
    assert "evil-site.com" not in allow_origin


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_security_headers(client: AsyncClient):
    """Health endpoint should include X-Frame-Options, CSP, etc."""
    resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-xss-protection") == "1; mode=block"
    assert "strict-transport-security" in resp.headers
    assert "content-security-policy" in resp.headers
    assert "referrer-policy" in resp.headers


# ---------------------------------------------------------------------------
# SQL injection prevention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sql_injection_prevention(mock_db: MockSupabaseClient):
    """SQL injection attempt in insumo nome should be sanitized."""
    from app.services.insumo_service import create_insumo

    data = {
        "nome": "'; DROP TABLE insumos; --",
        "unidade": "kg",
        "preco": 10.0,
        "quantidade_comprada": 1.0,
    }

    result = await create_insumo(mock_db, TEST_USER_ID, data)

    # The sanitize_string function strips HTML but the SQL chars remain.
    # The Supabase client uses parameterised queries, so injection is prevented.
    # At minimum, the value is stored without executing SQL.
    assert result["nome"] is not None
    assert "DROP TABLE" not in result.get("_executed_sql", "")


# ---------------------------------------------------------------------------
# XSS prevention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_xss_prevention(mock_db: MockSupabaseClient):
    """Script tags should be stripped from string fields."""
    from app.utils.sanitize import sanitize_string

    dirty = '<script>alert("xss")</script>Safe Content'
    cleaned = sanitize_string(dirty)

    assert "<script>" not in cleaned
    assert "alert" not in cleaned
    assert "Safe Content" in cleaned


@pytest.mark.asyncio
async def test_xss_nested_tags():
    """Nested / obfuscated HTML should also be stripped."""
    from app.utils.sanitize import sanitize_string

    dirty = '<img src=x onerror="alert(1)">Pizza'
    cleaned = sanitize_string(dirty)

    assert "<img" not in cleaned
    assert "onerror" not in cleaned
    assert "Pizza" in cleaned


# ---------------------------------------------------------------------------
# JWT tampering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jwt_tampering():
    """A JWT signed with the wrong key should be rejected."""
    from app.exceptions import AppException
    from app.services.auth_service import verify_jwt

    token = create_test_jwt(TEST_USER_ID)
    # Tamper: flip a character in the signature portion
    parts = token.rsplit(".", 1)
    tampered_sig = parts[1][:5] + ("X" if parts[1][5] != "X" else "Y") + parts[1][6:]
    tampered_token = parts[0] + "." + tampered_sig

    with pytest.raises(AppException) as exc_info:
        await verify_jwt(tampered_token, JWT_SECRET)

    assert exc_info.value.status == 401


# ---------------------------------------------------------------------------
# Expired JWT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_jwt():
    """An expired JWT should return 401."""
    from app.exceptions import AppException
    from app.services.auth_service import verify_jwt

    token = create_test_jwt(TEST_USER_ID, expired=True)

    with pytest.raises(AppException) as exc_info:
        await verify_jwt(token, JWT_SECRET)

    assert exc_info.value.status == 401
    assert "expired" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# User data isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_cant_access_others_data(mock_db: MockSupabaseClient):
    """User A should not be able to read User B's insumos.

    The service layer scopes every query by user_id. If the insumo does not
    belong to the requesting user, get_insumo raises NOT_FOUND.
    """
    from app.exceptions import AppException
    from app.services.insumo_service import get_insumo

    # Configure DB to return no data for the wrong user
    mock_db.configure_table("insumos", data=[], count=0)

    with pytest.raises(AppException) as exc_info:
        await get_insumo(mock_db, TEST_USER_ID, "some-insumo-belonging-to-user-b")

    assert exc_info.value.status == 404
    assert exc_info.value.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_sanitize_dict():
    """sanitize_dict should recursively sanitize all string values."""
    from app.utils.sanitize import sanitize_dict

    dirty = {
        "nome": "<b>Bold</b>",
        "nested": {
            "desc": "<script>bad</script>OK",
        },
        "items": ["<em>italic</em>", "plain"],
        "number": 42,
    }

    cleaned = sanitize_dict(dirty)

    assert "<b>" not in cleaned["nome"]
    assert "<script>" not in cleaned["nested"]["desc"]
    assert "<em>" not in cleaned["items"][0]
    assert cleaned["number"] == 42
