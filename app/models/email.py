"""Email template, sequence, and preference schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EmailTemplateCreate(BaseModel):
    """Payload to create a new email template."""

    slug: str = Field(..., description="Unique template slug (e.g. 'welcome')")
    name: str = Field(..., description="Human-readable template name")
    subject_template: str = Field(
        ..., description="Subject line with Jinja2 variables"
    )
    body_html: str = Field(..., description="HTML body with Jinja2 variables")
    body_text: str | None = Field(
        default=None, description="Plain-text fallback body"
    )
    variables_schema: dict | None = Field(
        default=None,
        description="JSON Schema describing expected template variables",
    )
    language: str = Field(
        default="pt-BR", description="Template language code"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "slug": "welcome",
                    "name": "Welcome Email",
                    "subject_template": "Bem-vindo, {{ nome_loja }}!",
                    "body_html": "<h1>Ola {{ nome_loja }}</h1><p>Obrigado por se cadastrar.</p>",
                    "body_text": "Ola {{ nome_loja }}! Obrigado por se cadastrar.",
                    "variables_schema": {
                        "type": "object",
                        "properties": {
                            "nome_loja": {"type": "string"}
                        },
                        "required": ["nome_loja"],
                    },
                    "language": "pt-BR",
                }
            ]
        }
    }


class EmailTemplateUpdate(BaseModel):
    """Partial update for an email template. All fields optional."""

    slug: str | None = Field(default=None, description="Template slug")
    name: str | None = Field(default=None, description="Template name")
    subject_template: str | None = Field(
        default=None, description="Subject line template"
    )
    body_html: str | None = Field(default=None, description="HTML body")
    body_text: str | None = Field(default=None, description="Plain-text body")
    variables_schema: dict | None = Field(
        default=None, description="Variables JSON Schema"
    )
    language: str | None = Field(default=None, description="Language code")
    is_active: bool | None = Field(
        default=None, description="Whether the template is active"
    )


class EmailTemplateResponse(BaseModel):
    """Email template as returned by the API."""

    id: UUID
    slug: str
    name: str
    subject_template: str
    body_html: str
    body_text: str | None = None
    variables_schema: dict = Field(default_factory=dict)
    language: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Email Sequences
# ---------------------------------------------------------------------------


class EmailSequenceCreate(BaseModel):
    """Payload to create a new automated email sequence."""

    name: str = Field(..., description="Sequence name")
    trigger_event: str = Field(
        ..., description="Event that triggers the sequence (e.g. 'user_signup')"
    )
    steps: list[dict] = Field(
        ...,
        description="Ordered list of steps, each with template_slug, delay_minutes, etc.",
    )
    is_active: bool = Field(
        default=True, description="Whether the sequence is active"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Onboarding",
                    "trigger_event": "user_signup",
                    "steps": [
                        {
                            "template_slug": "welcome",
                            "delay_minutes": 0,
                        },
                        {
                            "template_slug": "tips_day3",
                            "delay_minutes": 4320,
                        },
                    ],
                    "is_active": True,
                }
            ]
        }
    }


class EmailSequenceUpdate(BaseModel):
    """Partial update for an email sequence. All fields optional."""

    name: str | None = Field(default=None, description="Sequence name")
    trigger_event: str | None = Field(
        default=None, description="Trigger event"
    )
    steps: list[dict] | None = Field(default=None, description="Sequence steps")
    is_active: bool | None = Field(default=None, description="Active flag")


class EmailSequenceResponse(BaseModel):
    """Email sequence as returned by the API."""

    id: UUID
    name: str
    trigger_event: str
    steps: list[dict] = Field(default_factory=list)
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Sent Emails
# ---------------------------------------------------------------------------


class EmailSendResponse(BaseModel):
    """Record of a sent email."""

    id: UUID
    user_id: UUID
    template_id: UUID
    subject: str
    status: str = Field(
        ..., description="Delivery status (queued, sent, delivered, bounced, etc.)"
    )
    sent_at: datetime | None = None
    opened_at: datetime | None = None
    clicked_at: datetime | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Email Preferences
# ---------------------------------------------------------------------------


class EmailPreferencesUpdate(BaseModel):
    """User-facing email preference toggles."""

    marketing_opt_in: bool = Field(
        ..., description="Receive marketing / promotional emails"
    )
    transactional_enabled: bool = Field(
        ..., description="Receive transactional emails (receipts, alerts)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "marketing_opt_in": False,
                    "transactional_enabled": True,
                }
            ]
        }
    }
