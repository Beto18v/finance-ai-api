from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.core.finance import assume_utc_if_naive, get_timezone
from app.analytics.common import (
    AGGREGATED_TRANSACTION_DIRECTIONS,
    get_transaction_issue_reason,
    normalize_money,
    resolve_month_start,
)


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
    month_buckets: dict[tuple[int, int], dict[str, Decimal | date | int | str | None]] = {}
    missing_conversions: list[MonthlyBalanceIssue] = []

    for row in rows:
        if row.direction not in AGGREGATED_TRANSACTION_DIRECTIONS:
            continue

        month_start = resolve_month_start(
            occurred_at=row.occurred_at,
            timezone_name=timezone_name,
        )
        occurred_at = assume_utc_if_naive(row.occurred_at)
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

        issue_reason = get_transaction_issue_reason(
            amount_in_base_currency=row.amount_in_base_currency,
            snapshot_base_currency=row.base_currency,
            expected_base_currency=base_currency,
        )
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

        amount = normalize_money(row.amount_in_base_currency or Decimal("0"))
        if row.direction == "income":
            bucket["income"] = normalize_money(Decimal(bucket["income"]) + amount)
        else:
            bucket["expense"] = normalize_money(Decimal(bucket["expense"]) + amount)

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
            today = datetime.now(get_timezone(timezone_name)).date()
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


def _build_month_result(
    *,
    month_start: date,
    currency: str | None,
    income: Decimal,
    expense: Decimal,
    skipped_transactions: int,
) -> MonthlyBalanceMonth:
    normalized_income = normalize_money(income)
    normalized_expense = normalize_money(expense)

    return MonthlyBalanceMonth(
        month_start=month_start,
        currency=currency,
        income=normalized_income,
        expense=normalized_expense,
        balance=normalize_money(normalized_income - normalized_expense),
        skipped_transactions=skipped_transactions,
    )
