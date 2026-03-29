from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, case, distinct, func, or_
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.transaction import Transaction
from app.models.category import Category, CategoryDirection
from app.schemas.transaction import (
    TransactionAggregateTotal,
    TransactionCreate,
    TransactionListPage,
    TransactionListSummary,
    TransactionUpdate,
)
from app.services.exchange_rate_service import (
    apply_transaction_fx_snapshot,
    resolve_transaction_fx_snapshot,
)
from app.services.user_service import ensure_active_user


def create_transaction(
    db: Session,
    user_id: UUID,
    transaction_data: TransactionCreate,
):
    user = ensure_active_user(db, user_id)
    _ensure_transaction_amount_is_positive(transaction_data.amount)
    _ensure_transaction_currency_matches_user_base_currency(
        user_base_currency=user.base_currency,
        transaction_currency=transaction_data.currency,
    )

    category = db.query(Category).filter(
        Category.id == transaction_data.category_id,
        Category.user_id == user_id,
    ).first()

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    snapshot = resolve_transaction_fx_snapshot(
        db,
        user=user,
        transaction_currency=transaction_data.currency,
        occurred_at=transaction_data.occurred_at,
        amount=transaction_data.amount,
    )

    transaction = Transaction(
        user_id=user_id,
        category_id=transaction_data.category_id,
        amount=transaction_data.amount,
        currency=transaction_data.currency,
        description=transaction_data.description,
        occurred_at=transaction_data.occurred_at
    )
    apply_transaction_fx_snapshot(transaction, snapshot)

    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    return transaction


def get_transaction(db: Session, user_id: UUID, transaction_id: UUID) -> Transaction:
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == user_id,
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction


def list_transactions(
    db: Session,
    user_id: UUID,
    *,
    category_id: UUID | None = None,
    parent_category_id: UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    user_base_currency: str | None = None,
) -> TransactionListPage:
    query = _build_transactions_query(
        db,
        user_id,
        category_id=category_id,
        parent_category_id=parent_category_id,
        start_date=start_date,
        end_date=end_date,
    )
    total_count = query.with_entities(func.count(Transaction.id)).scalar() or 0
    items = (
        query.order_by(
            Transaction.occurred_at.desc(),
            Transaction.created_at.desc(),
            Transaction.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return TransactionListPage(
        items=items,
        total_count=int(total_count),
        limit=limit,
        offset=offset,
        summary=_build_transactions_summary(
            query=query,
            user_base_currency=user_base_currency,
        ),
    )


def update_transaction(
    db: Session,
    user_id: UUID,
    transaction_id: UUID,
    transaction_data: TransactionUpdate,
):
    user = ensure_active_user(db, user_id)
    transaction = get_transaction(db, user_id, transaction_id)
    updates = transaction_data.model_dump(exclude_unset=True)

    if "category_id" in updates and updates["category_id"] is not None:
        category = db.query(Category).filter(
            Category.id == updates["category_id"],
            Category.user_id == user_id,
        ).first()
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

    if "amount" in updates and updates["amount"] is not None:
        _ensure_transaction_amount_is_positive(updates["amount"])

    for field, value in updates.items():
        setattr(transaction, field, value)

    if "currency" in updates:
        _ensure_transaction_currency_matches_user_base_currency(
            user_base_currency=user.base_currency,
            transaction_currency=transaction.currency,
        )

    needs_fx_refresh = any(
        field in updates for field in ("amount", "currency", "occurred_at")
    ) or transaction.base_currency != user.base_currency
    if needs_fx_refresh:
        snapshot = resolve_transaction_fx_snapshot(
            db,
            user=user,
            transaction_currency=transaction.currency,
            occurred_at=transaction.occurred_at,
            amount=transaction.amount,
        )
        apply_transaction_fx_snapshot(transaction, snapshot)

    db.commit()
    db.refresh(transaction)
    return transaction


def delete_transaction(db: Session, user_id: UUID, transaction_id: UUID) -> None:
    transaction = get_transaction(db, user_id, transaction_id)
    db.delete(transaction)
    db.commit()


def _ensure_transaction_currency_matches_user_base_currency(
    *,
    user_base_currency: str | None,
    transaction_currency: str,
) -> None:
    # Product rule: Dinerance is single-currency in the user-facing flow.
    # FX snapshots stay internal and do not reopen multi-currency input.
    if not user_base_currency:
        raise HTTPException(
            status_code=409,
            detail="User base currency must be configured before creating transactions",
        )

    if transaction_currency != user_base_currency:
        raise HTTPException(
            status_code=409,
            detail="Transactions must use the user's base currency",
        )


def _ensure_transaction_amount_is_positive(amount: Decimal) -> None:
    if amount <= 0:
        raise HTTPException(
            status_code=422,
            detail="Transaction amount must be greater than zero",
        )


def _build_transactions_query(
    db: Session,
    user_id: UUID,
    *,
    category_id: UUID | None = None,
    parent_category_id: UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
):
    query = (
        db.query(Transaction)
        .join(Category, Transaction.category_id == Category.id)
        .filter(
            Transaction.user_id == user_id,
            Category.user_id == user_id,
        )
    )

    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if parent_category_id:
        query = query.filter(
            or_(
                Transaction.category_id == parent_category_id,
                Category.parent_id == parent_category_id,
            )
        )
    if start_date:
        query = query.filter(Transaction.occurred_at >= start_date)
    if end_date:
        query = query.filter(Transaction.occurred_at <= end_date)

    return query


def _build_transactions_summary(
    *,
    query,
    user_base_currency: str | None,
) -> TransactionListSummary:
    active_categories_count = (
        query.with_entities(func.count(distinct(Transaction.category_id))).scalar() or 0
    )

    if user_base_currency:
        return _build_base_currency_summary(
            query=query,
            user_base_currency=user_base_currency,
            active_categories_count=int(active_categories_count),
        )

    return _build_multi_currency_summary(
        query=query,
        active_categories_count=int(active_categories_count),
    )


def _build_base_currency_summary(
    *,
    query,
    user_base_currency: str,
    active_categories_count: int,
) -> TransactionListSummary:
    usable_amount = case(
        (Transaction.currency == user_base_currency, Transaction.amount),
        (
            and_(
                Transaction.base_currency == user_base_currency,
                Transaction.amount_in_base_currency.isnot(None),
            ),
            Transaction.amount_in_base_currency,
        ),
        else_=None,
    )

    income_total = _normalize_decimal(
        query.with_entities(
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                Category.direction == CategoryDirection.income,
                                usable_amount.isnot(None),
                            ),
                            usable_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            )
        ).scalar()
    )
    expense_total = _normalize_decimal(
        query.with_entities(
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                Category.direction == CategoryDirection.expense,
                                usable_amount.isnot(None),
                            ),
                            usable_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            )
        ).scalar()
    )
    usable_count = (
        query.with_entities(
            func.count(
                case(
                    (usable_amount.isnot(None), 1),
                    else_=None,
                )
            )
        ).scalar()
        or 0
    )
    skipped_transactions = (
        query.with_entities(
            func.count(
                case(
                    (
                        and_(
                            usable_amount.is_(None),
                            Category.direction.in_(
                                [
                                    CategoryDirection.income,
                                    CategoryDirection.expense,
                                ]
                            ),
                        ),
                        1,
                    ),
                    else_=None,
                )
            )
        ).scalar()
        or 0
    )

    income_totals = (
        [TransactionAggregateTotal(currency=user_base_currency, amount=income_total)]
        if income_total != 0
        else []
    )
    expense_totals = (
        [TransactionAggregateTotal(currency=user_base_currency, amount=expense_total)]
        if expense_total != 0
        else []
    )
    balance_totals = (
        [
            TransactionAggregateTotal(
                currency=user_base_currency,
                amount=income_total - expense_total,
            )
        ]
        if usable_count > 0
        else []
    )

    return TransactionListSummary(
        active_categories_count=active_categories_count,
        skipped_transactions=int(skipped_transactions),
        income_totals=income_totals,
        expense_totals=expense_totals,
        balance_totals=balance_totals,
    )


def _build_multi_currency_summary(
    *,
    query,
    active_categories_count: int,
) -> TransactionListSummary:
    grouped_totals = query.with_entities(
        Transaction.currency,
        Category.direction,
        func.coalesce(func.sum(Transaction.amount), 0),
    ).group_by(Transaction.currency, Category.direction)

    income_totals: dict[str, Decimal] = {}
    expense_totals: dict[str, Decimal] = {}
    balance_totals: dict[str, Decimal] = {}

    for currency, direction, amount in grouped_totals.all():
        normalized_amount = _normalize_decimal(amount)

        if direction == CategoryDirection.income:
            income_totals[currency] = normalized_amount
            balance_totals[currency] = balance_totals.get(currency, Decimal("0")) + normalized_amount
        elif direction == CategoryDirection.expense:
            expense_totals[currency] = normalized_amount
            balance_totals[currency] = balance_totals.get(currency, Decimal("0")) - normalized_amount

    return TransactionListSummary(
        active_categories_count=active_categories_count,
        skipped_transactions=0,
        income_totals=_serialize_totals(income_totals),
        expense_totals=_serialize_totals(expense_totals),
        balance_totals=_serialize_totals(balance_totals),
    )


def _serialize_totals(totals: dict[str, Decimal]) -> list[TransactionAggregateTotal]:
    return [
        TransactionAggregateTotal(currency=currency, amount=amount)
        for currency, amount in sorted(totals.items())
    ]


def _normalize_decimal(value: Decimal | int | float | None) -> Decimal:
    if value is None:
        return Decimal("0")

    if isinstance(value, Decimal):
        return value

    return Decimal(str(value))
