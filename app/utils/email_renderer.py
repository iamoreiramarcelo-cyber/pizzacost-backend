"""Email template rendering utilities for PizzaCost Pro."""

from __future__ import annotations

import re
from typing import Any


# Pattern to match {{variable_name}} placeholders
_VARIABLE_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _substitute(template: str, variables: dict[str, Any]) -> str:
    """Replace all ``{{variable}}`` placeholders in *template*.

    Unknown variables are left as-is so that partial rendering is safe.
    All variable values are converted to strings before substitution.
    """

    def _replacer(match: re.Match) -> str:
        key = match.group(1)
        if key in variables:
            return str(variables[key])
        return match.group(0)  # leave unknown placeholders untouched

    return _VARIABLE_PATTERN.sub(_replacer, template)


def render_template(
    subject_template: str,
    body_html: str,
    body_text: str | None,
    variables: dict[str, Any],
) -> dict[str, str]:
    """Render an email template by substituting ``{{variable}}`` placeholders.

    Args:
        subject_template: The email subject with optional placeholders.
        body_html: The HTML body with optional placeholders.
        body_text: An optional plain-text body with optional placeholders.
                   If ``None``, the returned ``text`` key will be an empty
                   string.
        variables: Mapping of variable names to their values.  Common keys
                   include ``user_name``, ``user_email``, ``app_url``,
                   ``store_name``, etc.

    Returns:
        A dict with keys ``subject``, ``html``, and ``text`` containing the
        fully rendered strings.
    """
    rendered_subject = _substitute(subject_template, variables)
    rendered_html = _substitute(body_html, variables)
    rendered_text = _substitute(body_text, variables) if body_text else ""

    return {
        "subject": rendered_subject,
        "html": rendered_html,
        "text": rendered_text,
    }


def get_user_variables(
    profile: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Build a common variables dict from a user profile and app settings.

    This factory centralises the mapping so that every email template
    receives a consistent set of substitution variables.

    Args:
        profile: User profile dict.  Expected keys (all optional):
                 ``nome``, ``email``, ``id``.
        settings: Application / store settings dict.  Expected keys
                  (all optional): ``app_url``, ``store_name``,
                  ``support_email``, ``logo_url``.

    Returns:
        A flat dict suitable for passing to :func:`render_template`.
    """
    return {
        "user_name": profile.get("nome", ""),
        "user_email": profile.get("email", ""),
        "user_id": profile.get("id", ""),
        "app_url": settings.get("app_url", ""),
        "store_name": settings.get("store_name", ""),
        "support_email": settings.get("support_email", ""),
        "logo_url": settings.get("logo_url", ""),
    }
