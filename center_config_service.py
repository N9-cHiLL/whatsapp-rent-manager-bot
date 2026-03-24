"""
Dynamic center/cabin configuration sourced from Google Sheets.

Source worksheet format ("Center Config"):
- Column A: Center Name
- Column B: Cabins (comma-separated list)
"""

from __future__ import annotations

import logging
from threading import Lock

from sheets_client import get_center_config_rows

logger = logging.getLogger(__name__)

CenterConfigMap = dict[str, list[str]]

_cache_lock = Lock()
_cache_map: CenterConfigMap | None = None


def _normalize_key(value: str | None) -> str:
    return (value or "").strip().casefold()


def _parse_center_config_rows(rows: list[list[str]]) -> CenterConfigMap:
    """
    Parse worksheet rows into canonical dict:
    {
      "MN": ["Cabin 8", "Studio 4"],
      "NA": ["Cabin 1", "Cabin 2"]
    }
    """
    parsed: CenterConfigMap = {}
    seen_center_keys: set[str] = set()

    for row in rows:
        if not row:
            continue
        center_raw = row[0] if len(row) >= 1 else ""
        cabins_raw = row[1] if len(row) >= 2 else ""

        center = str(center_raw).strip()
        if not center:
            continue

        center_key = _normalize_key(center)
        if center_key == "center name":
            # Skip header row if present.
            continue
        if center_key in seen_center_keys:
            logger.warning("Duplicate center in Center Config ignored: %s", center)
            continue

        cabins: list[str] = []
        seen_cabin_keys: set[str] = set()
        for token in str(cabins_raw).split(","):
            cabin = token.strip()
            if not cabin:
                continue
            cabin_key = _normalize_key(cabin)
            if cabin_key in seen_cabin_keys:
                continue
            seen_cabin_keys.add(cabin_key)
            cabins.append(cabin)

        seen_center_keys.add(center_key)
        parsed[center] = cabins

    return parsed


def refresh_center_config_cache() -> CenterConfigMap:
    """Force refresh cache from Google Sheets and return updated map."""
    global _cache_map
    rows = get_center_config_rows()
    parsed = _parse_center_config_rows(rows)
    with _cache_lock:
        _cache_map = parsed
    logger.info("Center Config cache refreshed: %s center(s)", len(parsed))
    return parsed


def get_center_config_map() -> CenterConfigMap:
    """
    Get cached center config map.
    Loads once lazily from sheet if cache is empty.
    """
    with _cache_lock:
        if _cache_map is not None:
            return dict(_cache_map)
    return dict(refresh_center_config_cache())


def get_valid_centers() -> list[str]:
    return sorted(get_center_config_map().keys())


def get_cabins_for_center(center_name: str) -> list[str]:
    cfg = get_center_config_map()
    resolved = resolve_center_name_dynamic(center_name, cfg)
    if not resolved:
        return []
    return list(cfg.get(resolved, []))


def resolve_center_name_dynamic(
    name: str | None, center_map: CenterConfigMap | None = None
) -> str | None:
    if not name or not str(name).strip():
        return None
    cfg = center_map if center_map is not None else get_center_config_map()
    name_key = _normalize_key(str(name))
    for canonical in cfg.keys():
        if _normalize_key(canonical) == name_key:
            return canonical
    return None


def resolve_cabin_name_dynamic(
    center_name: str, cabin_name: str | None, center_map: CenterConfigMap | None = None
) -> str | None:
    if not cabin_name or not str(cabin_name).strip():
        return None
    cfg = center_map if center_map is not None else get_center_config_map()
    resolved_center = resolve_center_name_dynamic(center_name, cfg)
    if not resolved_center:
        return None

    cabin_key = _normalize_key(str(cabin_name))
    for canonical in cfg.get(resolved_center, []):
        if _normalize_key(canonical) == cabin_key:
            return canonical
    return None
