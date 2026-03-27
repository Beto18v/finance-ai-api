from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from app.core.finance import assume_utc_if_naive, get_timezone

MONEY_QUANTIZER = Decimal("0.01")


@dataclass(slots=True)
class AnalyticsTransactionRow:
    transaction_id: UUID
    occurred_at: datetime
    direction: str
    source_currency: str
    base_currency: str | None
    amount_in_base_currency: Decimal | None


@dataclass(slots=True)
class MonthlyBalanceIssue:
    transaction_id: UUID
    occurred_at: datetime
    month_start: date
    source_currency: str
    target_currency: str | None
    reason: str


@dataclass(slots=True)
class MonthlyBalanceMonth:
    month_start: date
    currency: str | None
    income: Decimal
    expense: Decimal
    balance: Decimal
    skipped_transactions: int


@dataclass(slots=True)
class MonthlyBalanceOverview:
    currency: str | None
    current: MonthlyBalanceMonth
    series: list[MonthlyBalanceMonth]
    missing_conversions: list[MonthlyBalanceIssue]


def build_monthly_balance_overview(
    rows: list[AnalyticsTransactionRow],
    *,
    base_currency: str,
    timezone_name: str,
    year: int | None = None,
    month: int | None = None,
) -> MonthlyBalanceOverview:
    timezone = get_timezone(timezone_name)
    month_buckets: dict[tuple[int, int], dict[str, Decimal | date | int | str | None]] = {}
    missing_conversions: list[MonthlyBalanceIssue] = []

    for row in rows:
        occurred_at = assume_utc_if_naive(row.occurred_at)
        local_occurred_at = occurred_at.astimezone(timezone)
        month_start = date(local_occurred_at.year, local_occurred_at.month, 1)
        bucket_key = (month_start.year, month_start.month)
        bucket = month_buckets.setdefault(
            bucket_key,
            {
                "month_start": month_start,
                "currency": base_currency,
                "income": Decimal("0.00"),
                "expense": Decimal("0.00"),
                "skipped_transactions": 0,
            },
        )

        issue_reason = _get_issue_reason(row, base_currency)
        if issue_reason:
            bucket["skipped_transactions"] = int(bucket["skipped_transactions"]) + 1
            missing_conversions.append(
                MonthlyBalanceIssue(
                    transaction_id=row.transaction_id,
                    occurred_at=occurred_at,
                    month_start=month_start,
                    source_currency=row.source_currency,
                    target_currency=base_currency,
                    reason=issue_reason,
                )
            )
            continue

        amount = _normalize_money(row.amount_in_base_currency or Decimal("0"))
        if row.direction == "income":
            bucket["income"] = _normalize_money(Decimal(bucket["income"]) + amount)
        elif row.direction == "expense":
            bucket["expense"] = _normalize_money(Decimal(bucket["expense"]) + amount)
        else:
            bucket["skipped_transactions"] = int(bucket["skipped_transactions"]) + 1
            missing_conversions.append(
                MonthlyBalanceIssue(
                    transaction_id=row.transaction_id,
                    occurred_at=occurred_at,
                    month_start=month_start,
                    source_currency=row.source_currency,
                    target_currency=base_currency,
                    reason="unknown_category_direction",
                )
            )

    series = sorted(
        (
            _build_month_result(
                month_start=value["month_start"],
                currency=value["currency"],
                income=Decimal(value["income"]),
                expense=Decimal(value["expense"]),
                skipped_transactions=int(value["skipped_transactions"]),
            )
            for value in month_buckets.values()
        ),
        key=lambda item: item.month_start,
        reverse=True,
    )

    if year is None or month is None:
        if series:
            year = series[0].month_start.year
            month = series[0].month_start.month
        else:
            today = datetime.now(timezone).date()
            year = today.year
            month = today.month

    current_month = next(
        (
            item
            for item in series
            if item.month_start.year == year and item.month_start.month == month
        ),
        _build_month_result(
            month_start=date(year, month, 1),
            currency=base_currency,
            income=Decimal("0.00"),
            expense=Decimal("0.00"),
            skipped_transactions=0,
        ),
    )

    missing_conversions.sort(key=lambda item: item.occurred_at, reverse=True)

    return MonthlyBalanceOverview(
        currency=base_currency,
        current=current_month,
        series=series,
        missing_conversions=missing_conversions,
    )


def _get_issue_reason(
    row: AnalyticsTransactionRow,
    base_currency: str,
) -> str | None:
    if row.amount_in_base_currency is None:
        return "missing_fx_rate"

    if row.base_currency != base_currency:
        return "snapshot_base_currency_mismatch"

    return None


def _build_month_result(
    *,
    month_start: date,
    currency: str | None,
    income: Decimal,
    expense: Decimal,
    skipped_transactions: int,
) -> MonthlyBalanceMonth:
    normalized_income = _normalize_money(income)
    normalized_expense = _normalize_money(expense)

    return MonthlyBalanceMonth(
        month_start=month_start,
        currency=currency,
        income=normalized_income,
        expense=normalized_expense,
        balance=_normalize_money(normalized_income - normalized_expense),
        skipped_transactions=skipped_transactions,
    )


def _normalize_money(value: Decimal | int | float) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
