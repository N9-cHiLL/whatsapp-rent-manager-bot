"""
Google Sheets access via gspread + service account.

Ledger tab name: "Rent Ledger"
Columns: Timestamp, Date (IST), Month, Year, Center Name, Cabin ID, Amount, Payment Mode
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from config import get_settings

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_credentials():
    settings = get_settings()
    if settings.google_service_account_json:
        info = json.loads(settings.google_service_account_json)
        return Credentials.from_service_account_info(info, scopes=_SCOPES)
    if settings.google_application_credentials:
        p = Path(settings.google_application_credentials)
        return Credentials.from_service_account_file(str(p), scopes=_SCOPES)
    raise RuntimeError(
        "Set GOOGLE_APPLICATION_CREDENTIALS to a JSON path or GOOGLE_SERVICE_ACCOUNT_JSON"
    )


def get_worksheet():
    settings = get_settings()
    gc = gspread.authorize(_get_credentials())
    sh = gc.open_by_key(settings.spreadsheet_id)
    return sh.worksheet(settings.rent_ledger_worksheet)


def append_row(values: list) -> None:
    ws = get_worksheet()
    ws.append_row(values, value_input_option="USER_ENTERED")


def get_all_data_rows() -> list[list]:
    """Return all rows including header."""
    ws = get_worksheet()
    return ws.get_all_values()
