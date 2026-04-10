"""Authentication routes for PizzaCost Pro."""

import logging
import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from supabase import Client, create_client

from app.config import get_settings
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

logger = logging.getLogger(__name__)

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


@router.post("/reset-password")
@limiter.limit(AUTH_RATE_LIMIT)
async def request_reset(
    request: Request,
    data: dict,
    db: Client = Depends(get_supabase_client),
):
    """Generate 6-digit code and send to user's email via Resend."""
    import resend

    email = data.get("email", "").strip().lower()
    if not email:
        raise AppException("VALIDATION_ERROR", "Email obrigatorio.", 400)

    # Check if email exists
    user = db.table("profiles").select("id, email").eq("email", email).maybe_single().execute()
    # Always return success (don't reveal if email exists)

    if user.data:
        # Generate 6-digit code
        code = str(random.randint(100000, 999999))

        # Store code in DB (expires in 15 minutes)
        expires = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()

        db.table("password_reset_codes").upsert(
            {
                "email": email,
                "code": code,
                "expires_at": expires,
                "used": False,
            },
            on_conflict="email",
        ).execute()

        # Send via Resend
        settings = get_settings()
        if settings.RESEND_API_KEY:
            resend.api_key = settings.RESEND_API_KEY
            try:
                resend.Emails.send(
                    {
                        "from": settings.RESEND_FROM_EMAIL,
                        "to": email,
                        "subject": "Seu codigo de verificacao - PizzaCost Pro",
                        "html": f"""
                        <div style="font-family:'Plus Jakarta Sans',sans-serif;max-width:500px;margin:0 auto;padding:40px 32px;background:#fff;border-radius:16px">
                            <div style="text-align:center;margin-bottom:32px">
                                <div style="display:inline-block;background:#DC2626;padding:12px;border-radius:16px;margin-bottom:12px">
                                    <span style="color:white;font-size:24px;font-weight:bold">P</span>
                                </div>
                                <h1 style="color:#18181b;font-size:24px;margin:8px 0 0">PizzaCost Pro</h1>
                            </div>
                            <h2 style="color:#18181b;font-size:20px;text-align:center;margin-bottom:8px">Codigo de Verificacao</h2>
                            <p style="color:#71717a;text-align:center;margin-bottom:32px;font-size:14px">Use o codigo abaixo para redefinir sua senha:</p>
                            <div style="background:#f4f4f5;border-radius:12px;padding:24px;text-align:center;margin-bottom:32px">
                                <span style="font-size:36px;font-weight:800;letter-spacing:8px;color:#DC2626;font-family:monospace">{code}</span>
                            </div>
                            <p style="color:#a1a1aa;text-align:center;font-size:12px">Este codigo expira em 15 minutos.<br>Se voce nao solicitou isso, ignore este email.</p>
                        </div>
                        """,
                    }
                )
            except Exception as e:
                logger.error(f"Failed to send reset email: {e}")

    return {"data": {"message": "Se o email estiver cadastrado, voce recebera um codigo de verificacao."}}


@router.post("/verify-reset-code")
@limiter.limit(AUTH_RATE_LIMIT)
async def verify_code(
    request: Request,
    data: dict,
    db: Client = Depends(get_supabase_client),
):
    """Verify the 6-digit reset code."""
    email = data.get("email", "").strip().lower()
    code = data.get("code", "").strip()

    result = (
        db.table("password_reset_codes")
        .select("*")
        .eq("email", email)
        .eq("code", code)
        .eq("used", False)
        .maybe_single()
        .execute()
    )

    if not result.data:
        raise AppException("VALIDATION_ERROR", "Codigo invalido ou expirado.", 400)

    expires = result.data.get("expires_at", "")
    if expires and datetime.fromisoformat(expires.replace("Z", "+00:00")) < datetime.now(timezone.utc):
        raise AppException("VALIDATION_ERROR", "Codigo expirado. Solicite um novo.", 400)

    return {"data": {"valid": True}}


@router.post("/reset-password-confirm")
@limiter.limit(AUTH_RATE_LIMIT)
async def confirm_reset(
    request: Request,
    data: dict,
    db: Client = Depends(get_supabase_client),
):
    """Reset password with verified code."""
    email = data.get("email", "").strip().lower()
    code = data.get("code", "").strip()
    new_password = data.get("new_password", "")

    if len(new_password) < 8:
        raise AppException("VALIDATION_ERROR", "Senha deve ter pelo menos 8 caracteres.", 400)

    # Verify code again
    result = (
        db.table("password_reset_codes")
        .select("*")
        .eq("email", email)
        .eq("code", code)
        .eq("used", False)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise AppException("VALIDATION_ERROR", "Codigo invalido.", 400)

    expires = result.data.get("expires_at", "")
    if expires and datetime.fromisoformat(expires.replace("Z", "+00:00")) < datetime.now(timezone.utc):
        raise AppException("VALIDATION_ERROR", "Codigo expirado.", 400)

    # Mark code as used
    db.table("password_reset_codes").update({"used": True}).eq("email", email).eq("code", code).execute()

    # Find user and update password via Supabase Admin
    profile = db.table("profiles").select("id").eq("email", email).single().execute()
    if not profile.data:
        raise AppException("NOT_FOUND", "Usuario nao encontrado.", 404)

    # Use Supabase Admin to update password
    settings = get_settings()
    admin_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    admin_client.auth.admin.update_user_by_id(profile.data["id"], {"password": new_password})

    return {"data": {"message": "Senha redefinida com sucesso!"}}
