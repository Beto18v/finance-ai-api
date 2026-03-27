from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "UTC"
IDENTITY_RATE_SOURCE = "identity"


def normalize_currency_code(value: Any) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError("Currency must be a string")

    cleaned = value.strip().upper()
    if not cleaned:
        return None

    if len(cleaned) != 3 or not cleaned.isalpha():
        raise ValueError("Currency must be a 3-letter ISO code")

    return cleaned


def validate_currency_code(value: Any) -> str | None:
    return normalize_currency_code(value)


def normalize_timezone_name(value: Any) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError("Timezone must be a string")

    cleaned = value.strip()
    if not cleaned:
        return None

    try:
        ZoneInfo(cleaned)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Timezone must be a valid IANA timezone") from exc

    return cleaned


def resolve_timezone_name(value: str | None) -> str:
    normalized = normalize_timezone_name(value)
    return normalized or DEFAULT_TIMEZONE


def get_timezone(value: str | None) -> ZoneInfo:
    return ZoneInfo(resolve_timezone_name(value))


def ensure_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Datetime must include timezone information")

    return value


def assume_utc_if_naive(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)

    return value
