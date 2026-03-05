from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime

from app.core.auth import get_current_user_id
from app.database.session import get_db
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate, TransactionRead
from app.services.transaction_service import create_transaction

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.post("/", response_model=TransactionRead)
def create_transaction_endpoint(
    transaction_data: TransactionCreate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    return create_transaction(db, user_id, transaction_data)

@router.get("/", response_model=list[TransactionRead])
def get_transactions_endpoint(
    user_id=Depends(get_current_user_id),
    category_id: UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
    db: Session = Depends(get_db)
):

    query = db.query(Transaction).filter(
        Transaction.user_id == user_id
    )

    if category_id:
        query = query.filter(Transaction.category_id == category_id)

    if start_date:
        query = query.filter(Transaction.occurred_at >= start_date)

    if end_date:
        query = query.filter(Transaction.occurred_at <= end_date)

    query = query.order_by(Transaction.occurred_at.desc())

    return query.offset(offset).limit(limit).all()