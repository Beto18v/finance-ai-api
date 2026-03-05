from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.transaction import Transaction
from app.models.category import Category
from app.schemas.transaction import TransactionCreate
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
        merchant_name=transaction_data.merchant_name,
        occurred_at=transaction_data.occurred_at
    )

    db.add(transaction)
    db.commit()
    db.refresh(transaction)

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