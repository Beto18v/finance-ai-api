from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime

from app.core.auth import get_current_user_id
from app.database.session import get_db
from app.schemas.transaction import (
    TransactionCreate,
    TransactionListPage,
    TransactionRead,
    TransactionUpdate,
)
from app.services.transaction_service import (
    create_transaction,
    delete_transaction,
    get_transaction,
    list_transactions,
    update_transaction,
)
from app.services.user_service import ensure_active_user

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.post("/", response_model=TransactionRead)
def create_transaction_endpoint(
    transaction_data: TransactionCreate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    ensure_active_user(db, user_id)
    return create_transaction(db, user_id, transaction_data)

@router.get("/", response_model=TransactionListPage)
def get_transactions_endpoint(
    user_id=Depends(get_current_user_id),
    category_id: UUID | None = None,
    parent_category_id: UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    user = ensure_active_user(db, user_id)
    return list_transactions(
        db,
        user_id,
        category_id=category_id,
        parent_category_id=parent_category_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
        user_base_currency=user.base_currency,
    )


@router.get("/{transaction_id}", response_model=TransactionRead)
def get_transaction_endpoint(
    transaction_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return get_transaction(db, user_id, transaction_id)


@router.put("/{transaction_id}", response_model=TransactionRead)
def update_transaction_endpoint(
    transaction_id: UUID,
    transaction_data: TransactionUpdate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return update_transaction(db, user_id, transaction_id, transaction_data)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction_endpoint(
    transaction_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    delete_transaction(db, user_id, transaction_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
