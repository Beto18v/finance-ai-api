from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.finance import get_timezone
from app.models.category import Category, CategoryDirection
from app.models.transaction import Transaction
from app.schemas.analytics import (
    AnalyticsSummaryRead,
    AnalyticsSummaryTransactionRead,
)
from app.services.balance_service import (
    get_balance_overview_data,
    serialize_balance_overview,
)

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


def _get_recent_transactions_for_month(
    db: Session,
    *,
    user_id: UUID,
    month_start: date,
    timezone_name: str,
) -> list[AnalyticsSummaryTransactionRead]:
    start_utc, end_utc = _resolve_month_utc_range(
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


def _resolve_month_utc_range(
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
    next_month_start = _get_next_month_start(month_start)
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


def _get_next_month_start(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def _direction_to_text(direction: CategoryDirection | str) -> str:
    if isinstance(direction, CategoryDirection):
        return direction.value
    return str(direction)
