"""Authentication and user-profile service for PizzaCost Pro."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import jwt
from supabase import Client

from app.exceptions import AppException, not_found, unauthorized
from app.utils.sanitize import sanitize_string

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JWT verification
# ---------------------------------------------------------------------------

async def verify_jwt(token: str, jwt_secret: str) -> dict:
    """Decode and verify a Supabase JWT.

    Args:
        token: The raw JWT string (without the ``Bearer`` prefix).
        jwt_secret: The Supabase JWT secret used for HS256 verification.

    Returns:
        The decoded JWT payload as a dict.

    Raises:
        AppException: If the token is expired, malformed, or otherwise invalid.
    """
    try:
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise unauthorized("Token has expired.")
    except jwt.InvalidTokenError as exc:
        raise unauthorized(f"Invalid token: {exc}")


# ---------------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------------

async def get_user_profile(db: Client, user_id: str) -> dict | None:
    """Fetch a user profile by ``user_id``.

    Returns:
        The profile dict, or ``None`` if not found.
    """
    result = db.table("profiles").select("*").eq("id", user_id).execute()
    if result.data:
        return result.data[0]
    return None


async def create_profile(
    db: Client,
    user_id: str,
    email: str,
    nome_loja: str,
    telefone: str | None = None,
    role: str = "user",
) -> dict:
    """Insert a new row in the ``profiles`` table.

    Returns:
        The newly-created profile dict.
    """
    payload = {
        "id": user_id,
        "email": sanitize_string(email),
        "nome_loja": sanitize_string(nome_loja),
        "telefone": sanitize_string(telefone) if telefone else None,
        "role": role,
        "subscription_status": "free",
    }
    result = db.table("profiles").insert(payload).execute()
    return result.data[0]


# ---------------------------------------------------------------------------
# Full sign-up orchestration
# ---------------------------------------------------------------------------

async def signup_user(
    db: Client,
    email: str,
    password: str,
    nome_loja: str,
    telefone: str | None,
    marketing_opt_in: bool,
) -> dict:
    """Create a new user end-to-end.

    Steps:
        1. Create the auth user via Supabase Admin API.
        2. Create a ``profiles`` row.
        3. Create an ``email_preferences`` row.
        4. Log LGPD consent for terms acceptance and marketing opt-in.
        5. Trigger the welcome-email sequence.

    Returns:
        A dict with ``user`` (profile) and ``message``.

    Raises:
        AppException: On duplicate email or other Supabase errors.
    """
    # 1. Create auth user -------------------------------------------------
    try:
        auth_response = db.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
            }
        )
        user_id = auth_response.user.id
    except Exception as exc:
        error_msg = str(exc)
        if "already" in error_msg.lower() or "duplicate" in error_msg.lower():
            raise AppException(
                code="DUPLICATE_EMAIL",
                message="An account with this email already exists.",
                status=409,
            )
        logger.exception("Failed to create auth user")
        raise AppException(
            code="AUTH_ERROR",
            message="Failed to create user account.",
            status=500,
        )

    # 2. Create profile ---------------------------------------------------
    profile = await create_profile(
        db,
        user_id=str(user_id),
        email=email,
        nome_loja=nome_loja,
        telefone=telefone,
        role="user",
    )

    # 3. Email preferences ------------------------------------------------
    db.table("email_preferences").insert(
        {
            "user_id": str(user_id),
            "marketing_opt_in": marketing_opt_in,
            "transactional_opt_in": True,
        }
    ).execute()

    # 4. LGPD consent logs ------------------------------------------------
    now_iso = datetime.now(timezone.utc).isoformat()

    consent_entries = [
        {
            "user_id": str(user_id),
            "consent_type": "terms_of_service",
            "granted": True,
            "policy_version": "1.0",
            "created_at": now_iso,
        },
        {
            "user_id": str(user_id),
            "consent_type": "marketing",
            "granted": marketing_opt_in,
            "policy_version": "1.0",
            "created_at": now_iso,
        },
    ]
    db.table("consent_logs").insert(consent_entries).execute()

    # 5. Send welcome email (best-effort) ---------------------------------
    try:
        from app.services.email_service import send_transactional

        await send_transactional(
            db,
            user_id=str(user_id),
            template_slug="welcome",
            variables={"nome_loja": nome_loja},
        )
    except Exception:
        logger.warning("Welcome email could not be sent for user %s", user_id)

    return {
        "user": profile,
        "message": "Account created successfully.",
    }
