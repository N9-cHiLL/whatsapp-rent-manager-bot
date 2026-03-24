"""
Gemini parses user text into structured intent JSON.

If the model returns invalid JSON, we fall back to a generic unknown message.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Union

from google.api_core.exceptions import ResourceExhausted
from pydantic import ValidationError

from center_config_service import get_center_config_map
from config import IST, get_settings
from schemas import (
    ClarificationOutput,
    PaymentIntentOutput,
    UnknownIntentOutput,
    UnpaidQueryOutput,
)

logger = logging.getLogger(__name__)

ParsedIntent = Union[
    ClarificationOutput,
    PaymentIntentOutput,
    UnpaidQueryOutput,
    UnknownIntentOutput,
]


def _safe_response_text(resp: Any) -> str:
    """
    Gemini's `response.text` raises if the model returned no extractable text
    (blocked, safety, or empty candidates). Parse parts manually instead.
    """
    if resp is None:
        return ""
    try:
        t = getattr(resp, "text", None)
        if t:
            return str(t).strip()
    except Exception as e:
        logger.debug("response.text unavailable: %s", e)
    try:
        for cand in getattr(resp, "candidates", None) or []:
            content = getattr(cand, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", None) or []:
                text = getattr(part, "text", None)
                if text:
                    return str(text).strip()
    except Exception as e:
        logger.warning("Failed to read candidates: %s", e)
    # Log why there may be no text (helps debug refusals / empty JSON)
    try:
        pf = getattr(resp, "prompt_feedback", None)
        if pf and getattr(pf, "block_reason", None):
            logger.warning("Gemini prompt_feedback block_reason=%s", pf.block_reason)
    except Exception:
        pass
    return ""


def _build_system_instruction() -> str:
    center_config = get_center_config_map()
    center_config_json = json.dumps(center_config, ensure_ascii=True)
    now = datetime.now(IST)
    return f"""You are an intent parser for a WhatsApp rent bot for RAW co-working.

You are an assistant for a coworking space.
The ONLY valid centers and cabins are provided in this JSON map:
{center_config_json}

Current date/time (IST) for default year: {now.strftime("%Y-%m-%d %H:%M")} (year={now.year}).

Intents:
1) log_payment — User records a rent payment. Extract: center_name, cabin_id, amount, payment_mode.
   center_name and cabin_id MUST strictly match values from the JSON map.
   If center or cabin is missing, ambiguous, or not in the map, return intent "clarification" with a concise message.
   If amount is missing/invalid, return intent "clarification".
   Interpret "12k" as 12000.

2) unpaid_query — User asks who has not paid for a given calendar month (e.g. "Who hasn't paid rent for March in Center B?").
   Extract: center_name (required and must exist in JSON map), target_month (1-12), target_year (default to {now.year} if not specified).
   If center is missing or invalid, return intent "clarification".

3) unknown — Small talk or unrelated; optional custom message.

Output rules:
- Respond with ONLY a single JSON object, no markdown fences, no other text.
- The JSON must have key "intent" with one of: "log_payment", "unpaid_query", "clarification", "unknown".
- For "clarification": {{"intent":"clarification","message":"<user-facing reply>"}}
- For "log_payment": {{"intent":"log_payment","center_name":...,"cabin_id":...,"amount":...,"payment_mode":...}} (nulls only if you will use clarification instead — prefer clarification if center missing)
- For "unpaid_query": {{"intent":"unpaid_query","center_name":...,"target_month":<int>,"target_year":<int>}}
- For "unknown": {{"intent":"unknown","message":"..."}}
"""


def _extract_json_object(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def _parse_to_model(data: dict) -> ParsedIntent:
    intent = data.get("intent")
    if not intent:
        return UnknownIntentOutput()
    if intent == "clarification":
        return ClarificationOutput(message=str(data.get("message", "Please clarify.")))
    if intent == "log_payment":
        return PaymentIntentOutput(
            center_name=data.get("center_name"),
            cabin_id=str(data["cabin_id"]).strip() if data.get("cabin_id") is not None else None,
            amount=_coerce_float(data.get("amount")),
            payment_mode=str(data["payment_mode"]).strip() if data.get("payment_mode") else None,
        )
    if intent == "unpaid_query":
        try:
            return UnpaidQueryOutput(
                center_name=data.get("center_name"),
                target_month=int(data["target_month"]),
                target_year=int(data["target_year"]),
            )
        except (KeyError, TypeError, ValueError, ValidationError) as e:
            logger.warning("unpaid_query fields invalid: %s data=%s", e, data)
            return UnknownIntentOutput()
    if intent == "unknown":
        return UnknownIntentOutput(message=str(data.get("message", UnknownIntentOutput().message)))
    return UnknownIntentOutput()


def _coerce_float(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().lower().replace(",", "").replace(" ", "")
        if s.endswith("k") and len(s) > 1:
            try:
                return float(s[:-1]) * 1000
            except ValueError:
                return None
        try:
            return float(s)
        except ValueError:
            return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_message(user_text: str) -> ParsedIntent:
    import google.generativeai as genai

    try:
        settings = get_settings()
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            system_instruction=_build_system_instruction(),
        )
        gen_cfg = genai.GenerationConfig(
            temperature=0.2,
            response_mime_type="application/json",
        )
        resp = model.generate_content(user_text, generation_config=gen_cfg)
        raw = _safe_response_text(resp)
        if not raw:
            logger.warning("Empty Gemini response")
            return UnknownIntentOutput()
        try:
            data = _extract_json_object(raw)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("JSON parse failed: %s — raw: %s", e, raw[:500])
            return UnknownIntentOutput()

        try:
            return _parse_to_model(data)
        except (KeyError, TypeError, ValueError, ValidationError) as e:
            logger.warning("Model validation failed: %s data=%s", e, data)
            return UnknownIntentOutput()
    except ResourceExhausted as e:
        # 429 — quota / rate limit; sheet append never runs until this succeeds
        logger.warning("Gemini quota or rate limit: %s", e)
        return UnknownIntentOutput(
            message=(
                "Gemini API quota or rate limit reached — nothing was saved to the sheet. "
                "Wait and retry, or check limits/billing in Google AI Studio / Cloud Console."
            )
        )
    except Exception as e:
        logger.exception("Gemini request or parse failed: %s", e)
        return UnknownIntentOutput(
            message="Could not reach the AI service. Check GEMINI_API_KEY, model name, and network."
        )
