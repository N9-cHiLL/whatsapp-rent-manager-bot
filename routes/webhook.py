"""Twilio WhatsApp webhook."""

import logging
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request, Response

from centers_data import CABINS_BY_CENTER, VALID_CENTER_NAMES, resolve_center_name
from config import get_settings
from gemini_client import parse_message
from rent_logic import append_payment, unpaid_for_month
from schemas import (
    ClarificationOutput,
    PaymentIntentOutput,
    TwilioIncomingMessage,
    UnknownIntentOutput,
    UnpaidQueryOutput,
)
from twilio_client import send_whatsapp_reply, validate_request_if_configured

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


def _first(params: dict[str, list[str]], key: str) -> str:
    vals = params.get(key) or []
    return vals[0] if vals else ""


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/webhook")
async def twilio_webhook(request: Request) -> Response:
    """
    Twilio posts application/x-www-form-urlencoded data.
    We read the raw body once so X-Twilio-Signature validation matches the exact payload.
    """
    raw = await request.body()
    body_str = raw.decode("utf-8")
    settings = get_settings()

    if settings.validate_twilio_signature:
        base = (settings.public_base_url or "").rstrip("/")
        if not base:
            raise HTTPException(
                status_code=500,
                detail="PUBLIC_BASE_URL is required when VALIDATE_TWILIO_SIGNATURE is true",
            )
        sig = request.headers.get("X-Twilio-Signature", "")
        url = f"{base}{request.url.path}"
        if not validate_request_if_configured(url=url, post_body=body_str, signature=sig):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    params = parse_qs(body_str, keep_blank_values=True, strict_parsing=False)
    From = _first(params, "From")
    Body = _first(params, "Body").strip()

    msg = TwilioIncomingMessage(From=From, Body=Body)
    if not msg.From:
        return Response(content="", media_type="text/plain")

    if not msg.Body:
        await send_whatsapp_reply(
            to=msg.From,
            body="Send a message with center, cabin, amount, or ask who is unpaid for a month.",
        )
        return Response(content="", media_type="text/plain")

    try:
        parsed = parse_message(msg.Body)
    except Exception as e:
        logger.exception("Gemini parse failed: %s", e)
        await send_whatsapp_reply(
            to=msg.From,
            body="Something went wrong understanding your message. Please try again.",
        )
        return Response(content="", media_type="text/plain")

    reply: str

    if isinstance(parsed, ClarificationOutput):
        reply = parsed.message
    elif isinstance(parsed, UnknownIntentOutput):
        reply = parsed.message
    elif isinstance(parsed, PaymentIntentOutput):
        reply = await _handle_payment(parsed)
    elif isinstance(parsed, UnpaidQueryOutput):
        reply = await _handle_unpaid(parsed)
    else:
        reply = "Unsupported intent."

    await send_whatsapp_reply(to=msg.From, body=reply)
    return Response(content="", media_type="text/plain")


async def _handle_payment(p: PaymentIntentOutput) -> str:
    resolved = resolve_center_name(p.center_name)
    if not resolved:
        valid = ", ".join(sorted(VALID_CENTER_NAMES))
        return f"Which center? Please use one of: {valid}"

    center = resolved
    cabins = CABINS_BY_CENTER[center]
    cid = (p.cabin_id or "").strip()
    if not cid or cid not in cabins:
        return f"Invalid cabin for {center}. Valid cabins: {', '.join(cabins)}"

    if p.amount is None or p.amount <= 0:
        return "Please include a positive amount (e.g. 12000)."

    mode = (p.payment_mode or "unknown").strip() or "unknown"
    try:
        append_payment(
            center_name=center,
            cabin_id=cid,
            amount=p.amount,
            payment_mode=mode,
        )
    except Exception as e:
        logger.exception("Sheets append failed: %s", e)
        return "Could not save to the ledger. Try again later."

    return (
        f"Logged: {center} Cabin {cid} — ₹{p.amount:,.0f} ({mode}). "
        f"Timestamp recorded in IST."
    )


async def _handle_unpaid(p: UnpaidQueryOutput) -> str:
    resolved = resolve_center_name(p.center_name)
    if not resolved:
        valid = ", ".join(sorted(VALID_CENTER_NAMES))
        return f"Which center? Please use one of: {valid}"

    from calendar import month_name

    center = resolved
    try:
        unpaid = unpaid_for_month(center_name=center, month=p.target_month, year=p.target_year)
    except Exception as e:
        logger.exception("Unpaid query failed: %s", e)
        return "Could not read the ledger. Try again later."

    month_label = month_name[p.target_month]
    if not unpaid:
        return (
            f"All cabins have a payment recorded in {month_label} {p.target_year} "
            f"for {center} (by ledger date in IST)."
        )

    cabin_list = ", ".join(
        f"Cabin {c}" for c in sorted(unpaid, key=lambda x: (not str(x).isdigit(), int(x) if str(x).isdigit() else x))
    )
    return f"⚠️ Unpaid for {month_label} in {center}: {cabin_list}"
