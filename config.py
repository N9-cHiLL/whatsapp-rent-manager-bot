"""Application settings from environment variables."""

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

IST = ZoneInfo("Asia/Kolkata")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_from: str  # e.g. whatsapp:+14155238886
    spreadsheet_id: str
    google_application_credentials: Path | None = None
    # Optional: JSON string of service account (alternative to file path)
    google_service_account_json: str | None = None

    gemini_model: str = "gemini-2.5-flash"
    rent_ledger_worksheet: str = "Rent Ledger"

    # Optional Twilio request validation (set to true in production)
    validate_twilio_signature: bool = False
    public_base_url: str | None = None  # e.g. https://abc123.ngrok.io — required if validating signatures


@lru_cache
def get_settings() -> Settings:
    return Settings()
