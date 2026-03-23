"""
Rent business logic.

Pilot rule: a cabin counts as paid for calendar month M / year Y if there is at least one
ledger row for that (Center Name, Cabin ID) whose Timestamp (parsed as datetime in IST)
falls in that calendar month/year. See plan: timestamps are written in IST when logging.
"""

from __future__ import annotations

import logging
from calendar import month_name
from datetime import datetime
from typing import Iterable

from centers_data import CABINS_BY_CENTER
from config import IST
from sheets_client import append_row, get_all_data_rows

logger = logging.getLogger(__name__)

# New ledger rows: Timestamp, Date, Month, Year, Center Name, Cabin ID, Amount, Payment Mode
_NEW_ROW_MIN_LEN = 8


def _ts_center_cabin(row: list) -> tuple[str | None, str | None, str | None]:
    """Support legacy 5-column rows and new 8-column rows."""
    if len(row) >= _NEW_ROW_MIN_LEN:
        return row[0], row[4], row[5]
    if len(row) >= 3:
        return row[0], row[1], row[2]
    return None, None, None


def _parse_timestamp(cell: str) -> datetime | None:
    if not cell or not cell.strip():
        return None
    s = cell.strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S %Z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            if fmt.endswith("%z"):
                dt = datetime.strptime(s.replace("Z", "+00:00"), fmt)
            else:
                dt = datetime.strptime(s, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=IST)
            return dt.astimezone(IST)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return dt.astimezone(IST)
    except ValueError:
        pass
    logger.debug("Could not parse timestamp: %r", cell)
    return None


def append_payment(
    center_name: str,
    cabin_id: str,
    amount: float,
    payment_mode: str,
) -> None:
    # ISO-8601 with offset for reliable parsing in unpaid_for_month (IST).
    dt = datetime.now(IST)
    ts = dt.isoformat(timespec="seconds")
    date_ist = dt.strftime("%Y-%m-%d")
    month_ist = month_name[dt.month]
    year_ist = dt.year
    append_row(
        [
            ts,
            date_ist,
            month_ist,
            year_ist,
            center_name,
            str(cabin_id).strip(),
            amount,
            payment_mode,
        ]
    )


def _rows_after_header(rows: list[list]) -> Iterable[list]:
    if not rows:
        return []
    return rows[1:]


def unpaid_for_month(center_name: str, month: int, year: int) -> list[str]:
    """
    Cabins in center_name that have no ledger payment with timestamp in (month, year) IST.

    Compares against master list in CABINS_BY_CENTER.
    """
    master = set(CABINS_BY_CENTER.get(center_name, []))
    if not master:
        return []

    rows = get_all_data_rows()
    paid: set[str] = set()

    for row in _rows_after_header(rows):
        ts_s, cname, cid = _ts_center_cabin(row)
        if ts_s is None or cname is None or cid is None:
            continue
        if cname.strip() != center_name.strip():
            continue
        cid_norm = str(cid).strip()
        dt = _parse_timestamp(ts_s)
        if dt is None:
            continue
        if dt.month == month and dt.year == year:
            paid.add(cid_norm)

    return sorted(master - paid, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x))
