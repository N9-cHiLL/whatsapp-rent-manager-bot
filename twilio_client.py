"""Send outbound WhatsApp messages via Twilio REST API."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx

from config import get_settings

logger = logging.getLogger(__name__)


async def send_whatsapp_reply(to: str, body: str) -> None:
    """
    Send a WhatsApp message. `to` and From must be whatsapp:+E.164 numbers.
    """
    settings = get_settings()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
    data = {
        "From": settings.twilio_whatsapp_from,
        "To": to,
        "Body": body[:1600],
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(
            url,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            content=urlencode(data),
            timeout=30.0,
        )
    if r.status_code >= 400:
        logger.error("Twilio send failed %s: %s", r.status_code, r.text)


def validate_request_if_configured(url: str, post_body: str, signature: str) -> bool:
    """Validate X-Twilio-Signature when TWILIO_AUTH_TOKEN is set."""
    try:
        from twilio.request_validator import RequestValidator
    except ImportError:
        logger.warning("twilio package not installed; skipping signature validation")
        return True

    settings = get_settings()
    validator = RequestValidator(settings.twilio_auth_token)
    return bool(validator.validate(url, post_body, signature))
