from datetime import datetime, timezone, date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, extract, func
from sqlalchemy.orm import Session

from app.models.category import Category, CategoryDirection
from app.models.transaction import Transaction
from app.schemas.balance import BalanceMonthRead, BalanceOverviewRead


def get_balance_overview(
    db: Session,
    user_id: UUID,
    *,
    year: int | None = None,
    month: int | None = None,
) -> BalanceOverviewRead:
    year_expr = extract("year", Transaction.occurred_at)
    month_expr = extract("month", Transaction.occurred_at)

    monthly_rows = (
        db.query(
            year_expr.label("year"),
            month_expr.label("month"),
            func.coalesce(
                func.sum(
                    case(
                        (Category.direction == CategoryDirection.income, Transaction.amount),
                        else_=0,
                    )
                ),
                0,
            ).label("income"),
            func.coalesce(
                func.sum(
                    case(
                        (Category.direction == CategoryDirection.expense, Transaction.amount),
                        else_=0,
                    )
                ),
                0,
            ).label("expense"),
        )
        .join(Category, Transaction.category_id == Category.id)
        .filter(Transaction.user_id == user_id, Category.user_id == user_id)
        .group_by(year_expr, month_expr)
        .order_by(
            year_expr.desc(),
            month_expr.desc(),
        )
        .all()
    )

    series = [
        _build_month_summary(
            year=int(row.year),
            month=int(row.month),
            income=row.income,
            expense=row.expense,
        )
        for row in monthly_rows
    ]
    monthly_map = {
        (item.month_start.year, item.month_start.month): item for item in series
    }

    if year is None or month is None:
        if series:
            selected_month = series[0].month_start
            year = selected_month.year
            month = selected_month.month
        else:
            today = datetime.now(timezone.utc).date()
            year = today.year
            month = today.month

    current = monthly_map.get((year, month)) or _build_month_summary(
        year=year,
        month=month,
        income=Decimal("0.00"),
        expense=Decimal("0.00"),
    )

    return BalanceOverviewRead(current=current, series=series)


def _build_month_summary(
    *,
    year: int,
    month: int,
    income: Decimal,
    expense: Decimal,
) -> BalanceMonthRead:
    normalized_income = _normalize_decimal(income)
    normalized_expense = _normalize_decimal(expense)
    return BalanceMonthRead(
        month_start=date(year, month, 1),
        income=normalized_income,
        expense=normalized_expense,
        balance=normalized_income - normalized_expense,
    )


def _normalize_decimal(value: Decimal | int | float) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    return Decimal(str(value)).quantize(Decimal("0.01"))