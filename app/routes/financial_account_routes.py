from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.database.session import get_db
from app.schemas.financial_account import (
    FinancialAccountCreate,
    FinancialAccountRead,
    FinancialAccountUpdate,
)
from app.services.financial_account_service import (
    create_financial_account,
    delete_financial_account,
    get_financial_account,
    list_financial_accounts,
    update_financial_account,
)
from app.services.user_service import ensure_active_user

router = APIRouter(prefix="/financial-accounts", tags=["Financial Accounts"])


@router.post("/", response_model=FinancialAccountRead)
def create_financial_account_endpoint(
    account_data: FinancialAccountCreate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return create_financial_account(db, user_id, account_data)


@router.get("/", response_model=list[FinancialAccountRead])
def get_financial_accounts_endpoint(
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return list_financial_accounts(db, user_id)


@router.get("/{account_id}", response_model=FinancialAccountRead)
def get_financial_account_endpoint(
    account_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return get_financial_account(db, user_id, account_id)


@router.put("/{account_id}", response_model=FinancialAccountRead)
def update_financial_account_endpoint(
    account_id: UUID,
    account_data: FinancialAccountUpdate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return update_financial_account(db, user_id, account_id, account_data)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_financial_account_endpoint(
    account_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    delete_financial_account(db, user_id, account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
