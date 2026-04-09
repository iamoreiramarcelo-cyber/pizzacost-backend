"""Authentication routes for PizzaCost Pro."""

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.database import get_supabase_client, get_supabase_auth_client
from app.exceptions import AppException, unauthorized
from app.middleware.audit import audit_log
from app.middleware.rate_limit import limiter, AUTH_RATE_LIMIT
from app.models import (
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    SignupRequest,
    SuccessMessage,
    TokenResponse,
)
from app.services import auth_service
from app.services import activity_service

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit(AUTH_RATE_LIMIT)
async def login(
    request: Request,
    body: LoginRequest,
    db: Client = Depends(get_supabase_client),
):
    """Authenticate with email and password, returning JWT tokens."""
    auth_client = get_supabase_auth_client()

    try:
        auth_response = auth_client.auth.sign_in_with_password(
            {"email": body.email, "password": body.password}
        )
    except Exception as exc:
        error_msg = str(exc).lower()
        if "invalid" in error_msg or "credentials" in error_msg:
            raise unauthorized("Invalid email or password.")
        raise AppException(
            code="AUTH_ERROR",
            message="Authentication failed.",
            status=500,
        )

    session = auth_response.session
    user = auth_response.user

    if not session or not user:
        raise unauthorized("Invalid email or password.")

    # Fetch role from profiles
    profile_result = (
        db.table("profiles")
        .select("role")
        .eq("id", str(user.id))
        .maybe_single()
        .execute()
    )
    role = "user"
    if profile_result.data and profile_result.data.get("role"):
        role = profile_result.data["role"]

    # Audit log and activity tracking
    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=str(user.id),
        action="login",
        resource="auth",
        ip=ip,
    )
    await activity_service.track(db, user_id=str(user.id), action="login")

    return TokenResponse(
        access_token=session.access_token,
        token_type="bearer",
        expires_in=session.expires_in or 3600,
        user={
            "id": str(user.id),
            "email": user.email,
            "role": role,
        },
    )


@router.post("/signup", response_model=SuccessMessage, status_code=201)
@limiter.limit(AUTH_RATE_LIMIT)
async def signup(
    request: Request,
    body: SignupRequest,
    db: Client = Depends(get_supabase_client),
):
    """Create a new user account with profile and email preferences."""
    result = await auth_service.signup_user(
        db=db,
        email=body.email,
        password=body.password,
        nome_loja=body.nome_loja,
        telefone=body.telefone,
        marketing_opt_in=body.marketing_opt_in,
    )

    user_id = result["user"]["id"]
    ip = request.client.host if request.client else None
    await audit_log(
        db=db,
        user_id=str(user_id),
        action="signup",
        resource="auth",
        ip=ip,
    )
    await activity_service.track(db, user_id=str(user_id), action="signup")

    return SuccessMessage(message=result["message"])


@router.post("/logout", response_model=SuccessMessage)
async def logout(
    request: Request,
    db: Client = Depends(get_supabase_client),
):
    """Sign out the current user (revoke refresh token if possible)."""
    auth_header = request.headers.get("authorization", "")
    token = auth_header.replace("Bearer ", "").replace("bearer ", "").strip()

    if token:
        try:
            auth_client = get_supabase_auth_client()
            auth_client.auth.sign_out()
        except Exception:
            pass  # Best-effort sign out

    return SuccessMessage(message="Logged out successfully.")


@router.post("/password-reset", response_model=SuccessMessage)
@limiter.limit(AUTH_RATE_LIMIT)
async def password_reset(
    request: Request,
    body: PasswordResetRequest,
    db: Client = Depends(get_supabase_client),
):
    """Request a password reset email."""
    auth_client = get_supabase_auth_client()

    try:
        auth_client.auth.reset_password_email(body.email)
    except Exception:
        pass  # Always return success to prevent email enumeration

    return SuccessMessage(message="If an account with that email exists, a reset link has been sent.")


@router.post("/password-reset/confirm", response_model=SuccessMessage)
@limiter.limit(AUTH_RATE_LIMIT)
async def password_reset_confirm(
    request: Request,
    body: PasswordResetConfirm,
    db: Client = Depends(get_supabase_client),
):
    """Confirm a password reset with the token received via email."""
    auth_client = get_supabase_auth_client()

    try:
        auth_client.auth.update_user(
            {
                "password": body.new_password,
            }
        )
    except Exception as exc:
        error_msg = str(exc).lower()
        if "expired" in error_msg or "invalid" in error_msg:
            raise AppException(
                code="INVALID_TOKEN",
                message="Reset token is invalid or has expired.",
                status=400,
            )
        raise AppException(
            code="AUTH_ERROR",
            message="Failed to reset password.",
            status=500,
        )

    return SuccessMessage(message="Password has been reset successfully.")
