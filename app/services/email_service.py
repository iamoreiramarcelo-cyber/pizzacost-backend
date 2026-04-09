"""Email service for PizzaCost Pro (Resend integration)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from string import Template

import httpx
from supabase import Client

from app.config import get_settings
from app.exceptions import AppException, not_found

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def _render_template(body: str, variables: dict) -> str:
    """Render a template body with variable substitution.

    Uses ``$variable`` style placeholders via :class:`string.Template`.
    Unknown variables are left as-is.
    """
    return Template(body).safe_substitute(variables)


# ---------------------------------------------------------------------------
# Core email sending via Resend
# ---------------------------------------------------------------------------

async def _send_via_resend(to_email: str, subject: str, html_body: str) -> str | None:
    """Send an email through the Resend API.

    Returns:
        The Resend message ID on success, or ``None`` on failure.
    """
    settings = get_settings()
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not configured -- email not sent to %s", to_email)
        return None

    payload = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("id")
        except httpx.HTTPStatusError as exc:
            logger.error("Resend API error %s: %s", exc.response.status_code, exc.response.text)
            return None
        except Exception:
            logger.exception("Failed to send email via Resend to %s", to_email)
            return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def send_email(
    db: Client,
    user_id: str,
    template_slug: str,
    variables: dict,
) -> None:
    """Send an email to a user using a stored template.

    Respects email preferences: marketing templates require ``marketing_opt_in``.

    Args:
        db: Supabase client.
        user_id: Target user.
        template_slug: Slug of the email template in the ``email_templates`` table.
        variables: Dict of substitution variables.
    """
    # Load template
    tmpl_result = (
        db.table("email_templates")
        .select("*")
        .eq("slug", template_slug)
        .eq("active", True)
        .execute()
    )
    if not tmpl_result.data:
        logger.warning("Email template '%s' not found or inactive", template_slug)
        return

    template = tmpl_result.data[0]
    is_marketing = template.get("category", "transactional") == "marketing"

    # Check email preferences
    prefs_result = (
        db.table("email_preferences")
        .select("marketing_opt_in, transactional_opt_in")
        .eq("user_id", user_id)
        .execute()
    )
    prefs = prefs_result.data[0] if prefs_result.data else {}

    if is_marketing and not prefs.get("marketing_opt_in", False):
        logger.info("User %s opted out of marketing -- skipping '%s'", user_id, template_slug)
        return

    if not is_marketing and not prefs.get("transactional_opt_in", True):
        logger.info("User %s opted out of transactional -- skipping '%s'", user_id, template_slug)
        return

    # Get user email
    profile_result = (
        db.table("profiles")
        .select("email, nome_loja")
        .eq("id", user_id)
        .execute()
    )
    if not profile_result.data:
        logger.warning("Profile not found for user %s", user_id)
        return

    profile = profile_result.data[0]
    to_email = profile["email"]

    # Merge profile variables
    merged_vars = {
        "nome_loja": profile.get("nome_loja", ""),
        "email": to_email,
        **variables,
    }

    subject = _render_template(template["subject"], merged_vars)
    html_body = _render_template(template["body"], merged_vars)

    # Send
    resend_message_id = await _send_via_resend(to_email, subject, html_body)

    # Record send
    now = datetime.now(timezone.utc).isoformat()
    db.table("email_sends").insert(
        {
            "user_id": user_id,
            "template_slug": template_slug,
            "resend_message_id": resend_message_id,
            "to_email": to_email,
            "subject": subject,
            "status": "sent" if resend_message_id else "failed",
            "created_at": now,
        }
    ).execute()


async def send_transactional(
    db: Client,
    user_id: str,
    template_slug: str,
    variables: dict,
) -> None:
    """Send a transactional email, bypassing the marketing opt-in check.

    This is used for critical communications like password resets, welcome
    emails, and subscription confirmations.
    """
    # Load template
    tmpl_result = (
        db.table("email_templates")
        .select("*")
        .eq("slug", template_slug)
        .eq("active", True)
        .execute()
    )
    if not tmpl_result.data:
        logger.warning("Email template '%s' not found or inactive", template_slug)
        return

    template = tmpl_result.data[0]

    # Get user email
    profile_result = (
        db.table("profiles")
        .select("email, nome_loja")
        .eq("id", user_id)
        .execute()
    )
    if not profile_result.data:
        logger.warning("Profile not found for user %s", user_id)
        return

    profile = profile_result.data[0]
    to_email = profile["email"]

    merged_vars = {
        "nome_loja": profile.get("nome_loja", ""),
        "email": to_email,
        **variables,
    }

    subject = _render_template(template["subject"], merged_vars)
    html_body = _render_template(template["body"], merged_vars)

    resend_message_id = await _send_via_resend(to_email, subject, html_body)

    now = datetime.now(timezone.utc).isoformat()
    db.table("email_sends").insert(
        {
            "user_id": user_id,
            "template_slug": template_slug,
            "resend_message_id": resend_message_id,
            "to_email": to_email,
            "subject": subject,
            "status": "sent" if resend_message_id else "failed",
            "created_at": now,
        }
    ).execute()


# ---------------------------------------------------------------------------
# Sequences
# ---------------------------------------------------------------------------

async def trigger_sequence(
    db: Client,
    user_id: str,
    trigger_event: str,
) -> None:
    """Find active email sequences for the trigger event and schedule steps.

    Looks for sequences in ``email_sequences`` where ``trigger_event`` matches
    and ``active`` is True, then creates ``email_sequence_enrollments`` entries
    for each matching sequence.
    """
    sequences_result = (
        db.table("email_sequences")
        .select("*")
        .eq("trigger_event", trigger_event)
        .eq("active", True)
        .execute()
    )

    now = datetime.now(timezone.utc).isoformat()

    for seq in sequences_result.data:
        # Check if already enrolled
        existing = (
            db.table("email_sequence_enrollments")
            .select("id")
            .eq("user_id", user_id)
            .eq("sequence_id", seq["id"])
            .execute()
        )
        if existing.data:
            continue

        db.table("email_sequence_enrollments").insert(
            {
                "user_id": user_id,
                "sequence_id": seq["id"],
                "current_step_index": 0,
                "status": "active",
                "enrolled_at": now,
            }
        ).execute()

        logger.info(
            "User %s enrolled in sequence '%s' (trigger: %s)",
            user_id,
            seq.get("name", seq["id"]),
            trigger_event,
        )


async def process_sequence_step(
    db: Client,
    user_id: str,
    sequence_id: str,
    step_index: int,
) -> None:
    """Process a single step in an email sequence.

    Loads the sequence definition, finds the step at ``step_index``, sends
    the email, and advances the enrollment to the next step (or marks it
    complete).
    """
    seq_result = (
        db.table("email_sequences")
        .select("*")
        .eq("id", sequence_id)
        .execute()
    )
    if not seq_result.data:
        logger.warning("Sequence %s not found", sequence_id)
        return

    sequence = seq_result.data[0]
    steps = sequence.get("steps", [])

    if step_index >= len(steps):
        # All steps done
        db.table("email_sequence_enrollments").update(
            {"status": "completed"}
        ).eq("user_id", user_id).eq("sequence_id", sequence_id).execute()
        return

    step = steps[step_index]
    template_slug = step.get("template_slug")
    variables = step.get("variables", {})

    # Send the email for this step
    await send_transactional(db, user_id, template_slug, variables)

    # Advance to next step
    next_index = step_index + 1
    if next_index >= len(steps):
        db.table("email_sequence_enrollments").update(
            {
                "current_step_index": next_index,
                "status": "completed",
            }
        ).eq("user_id", user_id).eq("sequence_id", sequence_id).execute()
    else:
        db.table("email_sequence_enrollments").update(
            {"current_step_index": next_index}
        ).eq("user_id", user_id).eq("sequence_id", sequence_id).execute()


# ---------------------------------------------------------------------------
# Resend webhook status updates
# ---------------------------------------------------------------------------

async def update_email_status(
    db: Client,
    resend_message_id: str,
    status: str,
    opened_at: str | None = None,
    clicked_at: str | None = None,
) -> None:
    """Update an ``email_sends`` record based on a Resend webhook event.

    Args:
        resend_message_id: The Resend message ID.
        status: New status (``delivered``, ``opened``, ``clicked``, ``bounced``, etc.).
        opened_at: ISO timestamp of when the email was opened.
        clicked_at: ISO timestamp of when a link was clicked.
    """
    update_payload: dict = {"status": status}
    if opened_at:
        update_payload["opened_at"] = opened_at
    if clicked_at:
        update_payload["clicked_at"] = clicked_at

    result = (
        db.table("email_sends")
        .update(update_payload)
        .eq("resend_message_id", resend_message_id)
        .execute()
    )

    if not result.data:
        logger.warning("email_sends record not found for resend_message_id %s", resend_message_id)
