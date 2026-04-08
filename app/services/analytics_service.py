from __future__ import annotations

from datetime import date, timedelta

from fastapi import HTTPException
from uuid import UUID

from sqlalchemy import String, and_, case, cast, func, or_
from sqlalchemy.orm import Session

from app.analytics import (
    CategoryBreakdownRow,
    build_category_breakdown,
)
from app.analytics.common import (
    AGGREGATED_TRANSACTION_TYPES,
    normalize_money,
    resolve_month_utc_range,
)
from app.analytics.recurring_candidates import (
    ANALYSIS_WINDOW_DAYS,
    RecurringCandidate,
    RecurringCandidateRow,
    build_recurring_candidates,
)
from app.models.category import Category, CategoryDirection
from app.models.obligation import Obligation, ObligationStatus
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
    confirmed_obligations_by_key = _get_confirmed_obligations_by_recurring_candidate_key(
        db,
        user_id=user_id,
        candidates=overview.candidates,
    )

    return AnalyticsRecurringCandidatesRead(
        month_start=overview.month_start,
        history_window_start=overview.history_window_start,
        candidates=[
            AnalyticsRecurringCandidateRead(
                recurring_candidate_key=item.recurring_candidate_key,
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
                confirmed_obligation_id=confirmed_obligations_by_key.get(
                    item.recurring_candidate_key,
                    {},
                ).get("id"),
                confirmed_obligation_status=confirmed_obligations_by_key.get(
                    item.recurring_candidate_key,
                    {},
                ).get("status"),
            )
            for item in overview.candidates
        ],
    )


def _get_confirmed_obligations_by_recurring_candidate_key(
    db: Session,
    *,
    user_id: UUID,
    candidates: list[RecurringCandidate],
) -> dict[str, dict[str, UUID | str]]:
    recurring_candidate_keys = [item.recurring_candidate_key for item in candidates]
    normalized_keys = list(dict.fromkeys(recurring_candidate_keys))
    if not candidates:
        return {}

    status_rank = case(
        (Obligation.status == ObligationStatus.active, 0),
        (Obligation.status == ObligationStatus.paused, 1),
        else_=2,
    )
    rows = (
        db.query(
            Obligation.source_recurring_candidate_key,
            Obligation.id,
            Obligation.category_id,
            Obligation.name,
            Obligation.amount,
            Obligation.cadence,
            Obligation.status,
        )
        .filter(
            Obligation.user_id == user_id,
            or_(
                Obligation.source_recurring_candidate_key.in_(normalized_keys),
                Obligation.source_recurring_candidate_key.is_(None),
            ),
        )
        .order_by(
            status_rank.asc(),
            Obligation.created_at.asc(),
            Obligation.id.asc(),
        )
        .all()
    )

    confirmed_obligations_by_key: dict[str, dict[str, UUID | str]] = {}
    legacy_obligations_by_key: dict[str, dict[str, UUID | str]] = {}
    for row in rows:
        payload = {
            "id": row.id,
            "status": row.status.value,
        }
        if row.source_recurring_candidate_key is not None:
            if row.source_recurring_candidate_key in confirmed_obligations_by_key:
                continue
            confirmed_obligations_by_key[row.source_recurring_candidate_key] = payload
            continue

        legacy_key = _build_legacy_candidate_match_key(
            category_id=row.category_id,
            cadence=row.cadence.value,
            amount=row.amount,
            name=row.name,
        )
        legacy_obligations_by_key.setdefault(legacy_key, payload)

    for candidate in candidates:
        if candidate.direction != "expense":
            continue
        if candidate.recurring_candidate_key in confirmed_obligations_by_key:
            continue
        legacy_match = legacy_obligations_by_key.get(
            _build_legacy_candidate_match_key(
                category_id=candidate.category_id,
                cadence=candidate.cadence,
                amount=candidate.typical_amount,
                name=candidate.label,
            )
        )
        if legacy_match is not None:
            confirmed_obligations_by_key[candidate.recurring_candidate_key] = (
                legacy_match
            )

    return confirmed_obligations_by_key


def _build_legacy_candidate_match_key(
    *,
    category_id: UUID,
    cadence: str,
    amount,
    name: str,
) -> str:
    return "|".join(
        (
            str(category_id),
            cadence,
            str(normalize_money(amount)),
            _normalize_candidate_label(name),
        )
    )


def _normalize_candidate_label(value: str) -> str:
    return " ".join(str(value).split()).strip().lower()


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
