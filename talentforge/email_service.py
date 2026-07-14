"""Resend email delivery adapter."""

from __future__ import annotations

import os

import httpx


RESEND_EMAILS_URL = "https://api.resend.com/emails"


async def send_outreach_email(
    to_email: str,
    subject: str,
    html_content: str,
) -> str:
    """Send an approved outreach email and return Resend's message identifier."""
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_email = os.getenv("RESEND_FROM_EMAIL", "").strip()
    if not api_key or not from_email:
        raise RuntimeError("Resend email delivery is not configured.")

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            RESEND_EMAILS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                "html": html_content,
            },
        )
        response.raise_for_status()

    message_id = response.json().get("id")
    if not isinstance(message_id, str) or not message_id:
        raise RuntimeError("Resend did not return a message identifier.")
    return message_id
