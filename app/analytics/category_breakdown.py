from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.analytics.common import (
    VALID_CATEGORY_DIRECTIONS,
    get_transaction_issue_reason,
    normalize_money,
    normalize_percentage,
)


@dataclass(slots=True)
class CategoryBreakdownRow:
    transaction_id: UUID
    category_id: UUID
    category_name: str
    occurred_at: datetime
    direction: str
    source_currency: str
    base_currency: str | None
    amount_in_base_currency: Decimal | None


@dataclass(slots=True)
class CategoryBreakdownItem:
    category_id: UUID
    category_name: str
    direction: str
    amount: Decimal
    percentage: Decimal
    transaction_count: int


@dataclass(slots=True)
class CategoryBreakdownOverview:
    month_start: date
    currency: str | None
    direction: str | None
    total: Decimal
    skipped_transactions: int
    breakdown: list[CategoryBreakdownItem]


def build_category_breakdown(
    rows: list[CategoryBreakdownRow],
    *,
    base_currency: str,
    month_start: date,
    direction: str | None = None,
) -> CategoryBreakdownOverview:
    requested_direction = direction or None
    category_buckets: dict[
        UUID,
        dict[str, Decimal | int | str | UUID],
    ] = {}
    total = Decimal("0.00")
    skipped_transactions = 0

    for row in rows:
        row_direction = str(row.direction)
        if row_direction not in VALID_CATEGORY_DIRECTIONS:
            if requested_direction is None:
                skipped_transactions += 1
            continue

        if requested_direction and row_direction != requested_direction:
            continue

        issue_reason = get_transaction_issue_reason(
            amount_in_base_currency=row.amount_in_base_currency,
            snapshot_base_currency=row.base_currency,
            expected_base_currency=base_currency,
        )
        if issue_reason:
            skipped_transactions += 1
            continue

        amount = normalize_money(row.amount_in_base_currency or Decimal("0.00"))
        total = normalize_money(total + amount)
        bucket = category_buckets.setdefault(
            row.category_id,
            {
                "category_id": row.category_id,
                "category_name": row.category_name,
                "direction": row_direction,
                "amount": Decimal("0.00"),
                "transaction_count": 0,
            },
        )
        bucket["amount"] = normalize_money(Decimal(bucket["amount"]) + amount)
        bucket["transaction_count"] = int(bucket["transaction_count"]) + 1

    breakdown = [
        CategoryBreakdownItem(
            category_id=UUID(str(bucket["category_id"])),
            category_name=str(bucket["category_name"]),
            direction=str(bucket["direction"]),
            amount=Decimal(bucket["amount"]),
            percentage=normalize_percentage(
                Decimal("0.00")
                if total == 0
                else (Decimal(bucket["amount"]) * Decimal("100")) / total
            ),
            transaction_count=int(bucket["transaction_count"]),
        )
        for bucket in category_buckets.values()
    ]
    breakdown.sort(
        key=lambda item: (-item.amount, item.category_name.lower(), str(item.category_id))
    )

    return CategoryBreakdownOverview(
        month_start=month_start,
        currency=base_currency,
        direction=requested_direction,
        total=normalize_money(total),
        skipped_transactions=skipped_transactions,
        breakdown=breakdown,
    )
