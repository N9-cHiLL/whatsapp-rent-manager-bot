"""
Master list of cabins per center. Edit this dict to match RAW co-working locations.

Cabin IDs are strings so they match Google Sheet cells consistently (e.g. "4" not 4).
"""

CABINS_BY_CENTER: dict[str, list[str]] = {
    "Center A": ["1", "2", "3", "4", "5"],
    "Center B": ["1", "2", "3", "4"],
}

VALID_CENTER_NAMES = frozenset(CABINS_BY_CENTER.keys())


def resolve_center_name(name: str | None) -> str | None:
    """Match user/model text to a canonical center key (case-insensitive)."""
    if not name or not name.strip():
        return None
    n = name.strip().lower()
    for c in CABINS_BY_CENTER:
        if c.lower() == n:
            return c
    return None
