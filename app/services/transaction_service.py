from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.transaction import Transaction
from app.models.category import Category
from app.schemas.transaction import TransactionCreate, TransactionUpdate
import uuid


def create_transaction(
    db: Session,
    user_id,
    transaction_data: TransactionCreate
):

    category = db.query(Category).filter(
        Category.id == transaction_data.category_id,
        Category.user_id == user_id,
    ).first()

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    transaction = Transaction(
        id=uuid.uuid4(),
        user_id=user_id,
        category_id=transaction_data.category_id,
        amount=transaction_data.amount,
        currency=transaction_data.currency,
        description=transaction_data.description,
        occurred_at=transaction_data.occurred_at
    )

    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    return transaction


def get_transaction(db: Session, user_id, transaction_id: uuid.UUID):
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == user_id,
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction


def get_user_transactions(
    db: Session,
    user_id
):

    return db.query(Transaction).filter(
        Transaction.user_id == user_id
    ).order_by(
        Transaction.occurred_at.desc()
    ).all()


def update_transaction(
    db: Session,
    user_id,
    transaction_id: uuid.UUID,
    transaction_data: TransactionUpdate,
):
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

    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


def delete_transaction(db: Session, user_id, transaction_id: uuid.UUID) -> None:
    transaction = get_transaction(db, user_id, transaction_id)
    db.delete(transaction)
    db.commit()