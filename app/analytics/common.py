from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.core.finance import assume_utc_if_naive, get_timezone

MONEY_QUANTIZER = Decimal("0.01")
PERCENTAGE_QUANTIZER = Decimal("0.01")
VALID_CATEGORY_DIRECTIONS = {"income", "expense"}


def normalize_money(value: Decimal | int | float) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)


def normalize_percentage(value: Decimal | int | float) -> Decimal:
    return Decimal(str(value)).quantize(PERCENTAGE_QUANTIZER, rounding=ROUND_HALF_UP)


def get_transaction_issue_reason(
    *,
    amount_in_base_currency: Decimal | None,
    snapshot_base_currency: str | None,
    expected_base_currency: str,
) -> str | None:
    if amount_in_base_currency is None:
        return "missing_fx_rate"

    if snapshot_base_currency != expected_base_currency:
        return "snapshot_base_currency_mismatch"

    return None


def resolve_month_start(*, occurred_at: datetime, timezone_name: str) -> date:
    timezone_info = get_timezone(timezone_name)
    localized_occurred_at = assume_utc_if_naive(occurred_at).astimezone(timezone_info)
    return date(localized_occurred_at.year, localized_occurred_at.month, 1)


def resolve_month_utc_range(
    *,
    month_start: date,
    timezone_name: str,
) -> tuple[datetime, datetime]:
    timezone_info = get_timezone(timezone_name)
    start_local = datetime(
        month_start.year,
        month_start.month,
        1,
        tzinfo=timezone_info,
    )
    next_month_start = get_next_month_start(month_start)
    end_local = datetime(
        next_month_start.year,
        next_month_start.month,
        1,
        tzinfo=timezone_info,
    )
    return (
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )


def get_next_month_start(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)
