from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.analytics import AnalyticsTransactionRow, build_monthly_balance_overview
from app.models.category import Category, CategoryDirection
from app.models.transaction import Transaction
from app.services.user_service import ensure_active_user
from app.schemas.balance import (
    BalanceMonthRead,
    BalanceOverviewRead,
)


def get_balance_overview(
    db: Session,
    user_id: UUID,
    *,
    year: int | None = None,
    month: int | None = None,
) -> BalanceOverviewRead:
    user = ensure_active_user(db, user_id)
    if not user.base_currency:
        raise HTTPException(
            status_code=409,
            detail="User base currency must be configured before calculating balance",
        )

    # Analytics only consume base-currency snapshots so raw amounts from mixed
    # currencies never leak into a consolidated total.
    transaction_rows = (
        db.query(
            Transaction.id,
            Transaction.occurred_at,
            Transaction.currency,
            Transaction.base_currency,
            Transaction.amount_in_base_currency,
            Category.direction,
        )
        .join(Category, Transaction.category_id == Category.id)
        .filter(
            and_(
                Transaction.user_id == user_id,
                Category.user_id == user_id,
            )
        )
        .all()
    )

    overview = build_monthly_balance_overview(
        [
            AnalyticsTransactionRow(
                transaction_id=row.id,
                occurred_at=row.occurred_at,
                direction=_direction_to_text(row.direction),
                source_currency=row.currency,
                base_currency=row.base_currency,
                amount_in_base_currency=row.amount_in_base_currency,
            )
            for row in transaction_rows
        ],
        base_currency=user.base_currency,
        timezone_name=user.timezone or "UTC",
        year=year,
        month=month,
    )

    return BalanceOverviewRead(
        currency=overview.currency,
        current=BalanceMonthRead(
            month_start=overview.current.month_start,
            currency=overview.current.currency,
            income=overview.current.income,
            expense=overview.current.expense,
            balance=overview.current.balance,
            skipped_transactions=overview.current.skipped_transactions,
        ),
        series=[
            BalanceMonthRead(
                month_start=item.month_start,
                currency=item.currency,
                income=item.income,
                expense=item.expense,
                balance=item.balance,
                skipped_transactions=item.skipped_transactions,
            )
            for item in overview.series
        ],
    )


def _direction_to_text(direction: CategoryDirection | str) -> str:
    if isinstance(direction, CategoryDirection):
        return direction.value
    return str(direction)
