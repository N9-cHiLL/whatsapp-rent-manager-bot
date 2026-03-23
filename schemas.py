"""Pydantic models for Twilio payloads and Gemini structured output."""

from typing import Literal

from pydantic import BaseModel, Field


class TwilioIncomingMessage(BaseModel):
    """Subset of Twilio webhook fields we use."""

    From: str
    Body: str = ""


# --- Gemini JSON output (single schema, discriminated by intent) ---


class ClarificationOutput(BaseModel):
    intent: Literal["clarification"] = "clarification"
    message: str = Field(description="User-facing WhatsApp reply")


class PaymentIntentOutput(BaseModel):
    intent: Literal["log_payment"] = "log_payment"
    center_name: str | None = None
    cabin_id: str | None = None
    amount: float | None = None
    payment_mode: str | None = None


class UnpaidQueryOutput(BaseModel):
    intent: Literal["unpaid_query"] = "unpaid_query"
    center_name: str | None = None
    target_month: int = Field(ge=1, le=12)
    target_year: int


class UnknownIntentOutput(BaseModel):
    intent: Literal["unknown"] = "unknown"
    message: str = Field(
        default="I can log a payment (with center and cabin) or list unpaid cabins for a month. Try again?"
    )
