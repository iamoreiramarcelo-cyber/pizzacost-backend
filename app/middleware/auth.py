import logging
from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.config import get_settings
from app.database import get_supabase_client
from app.exceptions import unauthorized, forbidden

logger = logging.getLogger("pizzacost.auth")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


@dataclass
class UserContext:
    id: str
    email: str
    role: str


def _validate_token(token: str) -> dict:
    """Validate a Supabase JWT by calling Supabase Auth getUser.
    This works regardless of the signing algorithm (HS256 or ES256)."""
    from supabase import create_client
    settings = get_settings()
    # Create a temporary client with the user's token to validate it
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    try:
        response = client.auth.get_user(token)
        if response and response.user:
            return {
                "sub": response.user.id,
                "email": response.user.email,
            }
    except Exception as e:
        logger.debug(f"Token validation failed: {e}")
    return {}


def get_current_user(token: str = Depends(oauth2_scheme)) -> UserContext:
    """Validate JWT via Supabase Auth and return the current user context."""
    payload = _validate_token(token)

    user_id = payload.get("sub")
    email = payload.get("email")

    if not user_id:
        raise unauthorized("Token invalido ou expirado.")

    db = get_supabase_client()
    result = db.table("profiles").select("role").eq("id", user_id).maybe_single().execute()

    role = "user"
    if result.data and result.data.get("role"):
        role = result.data["role"]

    return UserContext(id=user_id, email=email or "", role=role)


def require_admin(user: UserContext = Depends(get_current_user)) -> UserContext:
    """Require the user to be an admin or super_admin."""
    if user.role not in ("admin", "super_admin"):
        raise forbidden("Acesso restrito a administradores.")
    return user


def require_super_admin(user: UserContext = Depends(get_current_user)) -> UserContext:
    """Require the user to be a super_admin."""
    if user.role != "super_admin":
        raise forbidden("Acesso restrito a super administradores.")
    return user


def get_optional_user(token: str | None = Depends(oauth2_scheme_optional)) -> UserContext | None:
    """Optionally validate JWT for public endpoints."""
    if token is None:
        return None

    payload = _validate_token(token)
    user_id = payload.get("sub")
    email = payload.get("email")

    if not user_id:
        return None

    db = get_supabase_client()
    result = db.table("profiles").select("role").eq("id", user_id).maybe_single().execute()

    role = "user"
    if result.data and result.data.get("role"):
        role = result.data["role"]

    return UserContext(id=user_id, email=email or "", role=role)
