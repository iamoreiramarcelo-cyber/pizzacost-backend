"""Input sanitization utilities for PizzaCost Pro."""

from typing import Any

import bleach


MAX_STRING_LENGTH = 10_000


def sanitize_string(value: str) -> str:
    """Sanitize a string by stripping HTML tags and trimming whitespace.

    Args:
        value: The raw string input.

    Returns:
        A cleaned string with no HTML tags, trimmed whitespace,
        and length capped at MAX_STRING_LENGTH characters.
    """
    if not isinstance(value, str):
        return value
    cleaned = bleach.clean(value, tags=[], attributes={}, strip=True)
    cleaned = cleaned.strip()
    return cleaned[:MAX_STRING_LENGTH]


def sanitize_dict(data: dict) -> dict:
    """Recursively sanitize all string values in a dictionary.

    Args:
        data: A dictionary potentially containing nested dicts, lists,
              and string values.

    Returns:
        A new dictionary with all string values sanitized.
    """
    if not isinstance(data, dict):
        return data
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = sanitize_string(value)
        elif isinstance(value, dict):
            result[key] = sanitize_dict(value)
        elif isinstance(value, list):
            result[key] = _sanitize_list(value)
        else:
            result[key] = value
    return result


def _sanitize_list(items: list) -> list:
    """Recursively sanitize all string values in a list.

    Args:
        items: A list potentially containing nested dicts, lists,
               and string values.

    Returns:
        A new list with all string values sanitized.
    """
    result: list[Any] = []
    for item in items:
        if isinstance(item, str):
            result.append(sanitize_string(item))
        elif isinstance(item, dict):
            result.append(sanitize_dict(item))
        elif isinstance(item, list):
            result.append(_sanitize_list(item))
        else:
            result.append(item)
    return result
