from datetime import date
from typing import Optional


def normalize_iso_date(value: str, field_name: str = "Date") -> str:
    cleaned = value.strip()
    try:
        parsed = date.fromisoformat(cleaned)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid date in YYYY-MM-DD format")
    if parsed.isoformat() != cleaned:
        raise ValueError(f"{field_name} must be a valid date in YYYY-MM-DD format")
    return cleaned


def normalize_optional_iso_date(
    value: Optional[str], field_name: str = "Date"
) -> Optional[str]:
    if value is None or not value.strip():
        return None
    return normalize_iso_date(value, field_name)
