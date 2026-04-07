from __future__ import annotations

from datetime import date, timedelta

from fastapi import HTTPException
from uuid import UUID

from sqlalchemy import String, and_, cast, func
from sqlalchemy.orm import Session

from app.analytics import (
    CategoryBreakdownRow,
    build_category_breakdown,
)
from app.analytics.common import (
    AGGREGATED_TRANSACTION_TYPES,
    resolve_month_utc_range,
)
from app.analytics.recurring_candidates import (
    ANALYSIS_WINDOW_DAYS,
    RecurringCandidateRow,
    build_recurring_candidates,
)
from app.models.category import Category, CategoryDirection
from app.models.transaction import Transaction, TransactionType
from app.schemas.analytics import (
    AnalyticsCategoryBreakdownItemRead,
    AnalyticsCategoryBreakdownRead,
    AnalyticsRecurringCandidateRead,
    AnalyticsRecurringCandidatesRead,
    AnalyticsSummaryRead,
    AnalyticsSummaryTransactionRead,
)
from app.services.balance_service import (
    get_balance_overview_data,
    serialize_balance_overview,
)
from app.services.financial_account_service import get_financial_account_for_user
from app.services.user_service import ensure_active_user

RECENT_TRANSACTIONS_LIMIT = 5


def get_analytics_summary(
    db: Session,
    user_id: UUID,
    *,
    year: int | None = None,
    month: int | None = None,
    financial_account_id: UUID | None = None,
) -> AnalyticsSummaryRead:
    user, overview = get_balance_overview_data(
        db,
        user_id,
        year=year,
        month=month,
        financial_account_id=financial_account_id,
    )
    balance_overview = serialize_balance_overview(overview)
    recent_transactions = _get_recent_transactions_for_month(
        db,
        user_id=user_id,
        month_start=overview.current.month_start,
        timezone_name=user.timezone or "UTC",
        financial_account_id=financial_account_id,
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
    financial_account_id: UUID | None = None,
) -> AnalyticsCategoryBreakdownRead:
    user = ensure_active_user(db, user_id)
    if not user.base_currency:
        raise HTTPException(
            status_code=409,
            detail="User base currency must be configured before calculating balance",
        )

    if financial_account_id is not None:
        get_financial_account_for_user(db, user_id, financial_account_id)

    month_start = date(year, month, 1)
    start_utc, end_utc = resolve_month_utc_range(
        month_start=month_start,
        timezone_name=user.timezone or "UTC",
    )
    filters = [
        Transaction.user_id == user_id,
        Category.user_id == user_id,
        Transaction.occurred_at >= start_utc,
        Transaction.occurred_at < end_utc,
        Transaction.transaction_type.in_(AGGREGATED_TRANSACTION_TYPES),
    ]
    if financial_account_id is not None:
        filters.append(Transaction.financial_account_id == financial_account_id)

    rows = (
        db.query(
            Transaction.id,
            Transaction.category_id,
            Transaction.occurred_at,
            Transaction.currency,
            Transaction.base_currency,
            Transaction.amount_in_base_currency,
            Category.name.label("category_name"),
            Transaction.transaction_type,
        )
        .join(Category, Transaction.category_id == Category.id)
        .filter(and_(*filters))
        .all()
    )
    breakdown = build_category_breakdown(
        [
            CategoryBreakdownRow(
                transaction_id=row.id,
                category_id=row.category_id,
                category_name=row.category_name,
                occurred_at=row.occurred_at,
                direction=_direction_to_text(row.transaction_type),
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


def get_analytics_recurring_candidates(
    db: Session,
    user_id: UUID,
    *,
    year: int,
    month: int,
    financial_account_id: UUID | None = None,
) -> AnalyticsRecurringCandidatesRead:
    user = ensure_active_user(db, user_id)

    if financial_account_id is not None:
        get_financial_account_for_user(db, user_id, financial_account_id)

    month_start = date(year, month, 1)
    analysis_window_start = month_start - timedelta(days=ANALYSIS_WINDOW_DAYS)
    start_utc, _ = resolve_month_utc_range(
        month_start=analysis_window_start,
        timezone_name=user.timezone or "UTC",
    )
    _, end_utc = resolve_month_utc_range(
        month_start=month_start,
        timezone_name=user.timezone or "UTC",
    )

    filters = [
        Transaction.user_id == user_id,
        Category.user_id == user_id,
        Transaction.occurred_at >= start_utc,
        Transaction.occurred_at < end_utc,
        Transaction.transaction_type.in_(AGGREGATED_TRANSACTION_TYPES),
    ]
    if financial_account_id is not None:
        filters.append(Transaction.financial_account_id == financial_account_id)

    rows = (
        db.query(
            Transaction.id,
            Transaction.category_id,
            Transaction.occurred_at,
            Transaction.amount,
            Transaction.currency,
            Transaction.description,
            Category.name.label("category_name"),
            Transaction.transaction_type,
        )
        .join(Category, Transaction.category_id == Category.id)
        .filter(and_(*filters))
        .all()
    )

    overview = build_recurring_candidates(
        [
            RecurringCandidateRow(
                transaction_id=row.id,
                category_id=row.category_id,
                category_name=row.category_name,
                occurred_at=row.occurred_at,
                amount=row.amount,
                currency=row.currency,
                description=row.description,
                direction=_direction_to_text(row.transaction_type),
            )
            for row in rows
        ],
        month_start=month_start,
        timezone_name=user.timezone or "UTC",
    )

    return AnalyticsRecurringCandidatesRead(
        month_start=overview.month_start,
        history_window_start=overview.history_window_start,
        candidates=[
            AnalyticsRecurringCandidateRead(
                label=item.label,
                description=item.description,
                category_id=item.category_id,
                category_name=item.category_name,
                direction=item.direction,
                cadence=item.cadence,
                match_basis=item.match_basis,
                amount_pattern=item.amount_pattern,
                currency=item.currency,
                typical_amount=item.typical_amount,
                amount_min=item.amount_min,
                amount_max=item.amount_max,
                occurrence_count=item.occurrence_count,
                interval_days=item.interval_days,
                first_occurred_at=item.first_occurred_at,
                last_occurred_at=item.last_occurred_at,
            )
            for item in overview.candidates
        ],
    )


def _get_recent_transactions_for_month(
    db: Session,
    *,
    user_id: UUID,
    month_start: date,
    timezone_name: str,
    financial_account_id: UUID | None = None,
) -> list[AnalyticsSummaryTransactionRead]:
    start_utc, end_utc = resolve_month_utc_range(
        month_start=month_start,
        timezone_name=timezone_name,
    )

    filters = [
        Transaction.user_id == user_id,
        Transaction.occurred_at >= start_utc,
        Transaction.occurred_at < end_utc,
        Transaction.transaction_type.in_(AGGREGATED_TRANSACTION_TYPES),
    ]
    if financial_account_id is not None:
        filters.append(Transaction.financial_account_id == financial_account_id)

    rows = (
        db.query(
            Transaction.id,
            Transaction.category_id,
            Transaction.financial_account_id,
            Transaction.amount,
            Transaction.currency,
            Transaction.base_currency,
            Transaction.amount_in_base_currency,
            Transaction.description,
            Transaction.occurred_at,
            func.coalesce(
                Category.name,
                cast(Transaction.transaction_type, String),
            ).label("category_name"),
            Transaction.transaction_type,
        )
        .outerjoin(Category, Transaction.category_id == Category.id)
        .filter(and_(*filters))
        .order_by(Transaction.occurred_at.desc(), Transaction.created_at.desc())
        .limit(RECENT_TRANSACTIONS_LIMIT)
        .all()
    )

    return [
        AnalyticsSummaryTransactionRead(
            id=row.id,
            category_id=row.category_id,
            financial_account_id=row.financial_account_id,
            category_name=row.category_name,
            direction=_direction_to_text(row.transaction_type),
            amount=row.amount,
            currency=row.currency,
            base_currency=row.base_currency,
            amount_in_base_currency=row.amount_in_base_currency,
            description=row.description,
            occurred_at=row.occurred_at,
        )
        for row in rows
    ]


def _direction_to_text(direction: TransactionType | CategoryDirection | str) -> str:
    if isinstance(direction, (TransactionType, CategoryDirection)):
        return direction.value
    return str(direction)
