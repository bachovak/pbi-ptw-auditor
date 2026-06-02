"""Shared utility helpers."""

from __future__ import annotations


def redact_email(email: str) -> str:
    """Mask an email address for safe external sharing.

    Example: ``john@gmail.com`` → ``j****@gmail.com``

    Args:
        email: Raw email address string.

    Returns:
        Masked email, or the original string if it has no ``@`` sign.
    """
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        return f"****@{domain}"
    return f"{local[0]}****@{domain}"
