from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.analytics import (
    CategoryBreakdownRow,
    build_category_breakdown,
)
from app.analytics.common import resolve_month_utc_range
from app.models.category import Category, CategoryDirection
from app.models.transaction import Transaction
from app.schemas.analytics import (
    AnalyticsCategoryBreakdownItemRead,
    AnalyticsCategoryBreakdownRead,
    AnalyticsSummaryRead,
    AnalyticsSummaryTransactionRead,
)
from app.services.balance_service import (
    get_balance_overview_data,
    serialize_balance_overview,
)
from app.services.user_service import ensure_active_user

RECENT_TRANSACTIONS_LIMIT = 5


def get_analytics_summary(
    db: Session,
    user_id: UUID,
    *,
    year: int | None = None,
    month: int | None = None,
) -> AnalyticsSummaryRead:
    user, overview = get_balance_overview_data(db, user_id, year=year, month=month)
    balance_overview = serialize_balance_overview(overview)
    recent_transactions = _get_recent_transactions_for_month(
        db,
        user_id=user_id,
        month_start=overview.current.month_start,
        timezone_name=user.timezone or "UTC",
    )

    return AnalyticsSummaryRead(
        currency=balance_overview.currency,
        current=balance_overview.current,
        series=balance_overview.series,
        recent_transactions=recent_transactions,
    )


def get_analytics_category_breakdown(
    db: Session,
    user_id: UUID,
    *,
    year: int,
    month: int,
    direction: CategoryDirection | None = None,
) -> AnalyticsCategoryBreakdownRead:
    user = ensure_active_user(db, user_id)
    if not user.base_currency:
        raise HTTPException(
            status_code=409,
            detail="User base currency must be configured before calculating balance",
        )

    month_start = date(year, month, 1)
    start_utc, end_utc = resolve_month_utc_range(
        month_start=month_start,
        timezone_name=user.timezone or "UTC",
    )
    rows = (
        db.query(
            Transaction.id,
            Transaction.category_id,
            Transaction.occurred_at,
            Transaction.currency,
            Transaction.base_currency,
            Transaction.amount_in_base_currency,
            Category.name.label("category_name"),
            Category.direction,
        )
        .join(Category, Transaction.category_id == Category.id)
        .filter(
            and_(
                Transaction.user_id == user_id,
                Category.user_id == user_id,
                Transaction.occurred_at >= start_utc,
                Transaction.occurred_at < end_utc,
            )
        )
        .all()
    )
    breakdown = build_category_breakdown(
        [
            CategoryBreakdownRow(
                transaction_id=row.id,
                category_id=row.category_id,
                category_name=row.category_name,
                occurred_at=row.occurred_at,
                direction=_direction_to_text(row.direction),
                source_currency=row.currency,
                base_currency=row.base_currency,
                amount_in_base_currency=row.amount_in_base_currency,
            )
            for row in rows
        ],
        base_currency=user.base_currency,
        month_start=month_start,
        direction=_direction_to_text(direction) if direction is not None else None,
    )

    return AnalyticsCategoryBreakdownRead(
        month_start=breakdown.month_start,
        currency=breakdown.currency,
        direction=breakdown.direction,
        total=breakdown.total,
        skipped_transactions=breakdown.skipped_transactions,
        breakdown=[
            AnalyticsCategoryBreakdownItemRead(
                category_id=item.category_id,
                category_name=item.category_name,
                direction=item.direction,
                amount=item.amount,
                percentage=item.percentage,
                transaction_count=item.transaction_count,
            )
            for item in breakdown.breakdown
        ],
    )


def _get_recent_transactions_for_month(
    db: Session,
    *,
    user_id: UUID,
    month_start: date,
    timezone_name: str,
) -> list[AnalyticsSummaryTransactionRead]:
    start_utc, end_utc = resolve_month_utc_range(
        month_start=month_start,
        timezone_name=timezone_name,
    )

    rows = (
        db.query(
            Transaction.id,
            Transaction.category_id,
            Transaction.amount,
            Transaction.currency,
            Transaction.base_currency,
            Transaction.amount_in_base_currency,
            Transaction.description,
            Transaction.occurred_at,
            Category.name.label("category_name"),
            Category.direction,
        )
        .join(Category, Transaction.category_id == Category.id)
        .filter(
            and_(
                Transaction.user_id == user_id,
                Category.user_id == user_id,
                Transaction.occurred_at >= start_utc,
                Transaction.occurred_at < end_utc,
            )
        )
        .order_by(Transaction.occurred_at.desc(), Transaction.created_at.desc())
        .limit(RECENT_TRANSACTIONS_LIMIT)
        .all()
    )

    return [
        AnalyticsSummaryTransactionRead(
            id=row.id,
            category_id=row.category_id,
            category_name=row.category_name,
            direction=_direction_to_text(row.direction),
            amount=row.amount,
            currency=row.currency,
            base_currency=row.base_currency,
            amount_in_base_currency=row.amount_in_base_currency,
            description=row.description,
            occurred_at=row.occurred_at,
        )
        for row in rows
    ]


def _direction_to_text(direction: CategoryDirection | str) -> str:
    if isinstance(direction, CategoryDirection):
        return direction.value
    return str(direction)
