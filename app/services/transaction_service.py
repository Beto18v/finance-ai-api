from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.transaction import Transaction
from app.models.category import Category
from app.schemas.transaction import TransactionCreate, TransactionUpdate
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
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Transaction]:
    query = db.query(Transaction).filter(Transaction.user_id == user_id)
    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if start_date:
        query = query.filter(Transaction.occurred_at >= start_date)
    if end_date:
        query = query.filter(Transaction.occurred_at <= end_date)
    return query.order_by(Transaction.occurred_at.desc()).offset(offset).limit(limit).all()


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
