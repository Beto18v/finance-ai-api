from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.database.session import get_db
from app.schemas.ledger import AdjustmentCreate, LedgerMovementRead
from app.services.adjustment_service import create_adjustment, delete_adjustment
from app.services.user_service import ensure_active_user

router = APIRouter(prefix="/adjustments", tags=["Adjustments"])


@router.post("/", response_model=LedgerMovementRead)
def create_adjustment_endpoint(
    adjustment_data: AdjustmentCreate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return create_adjustment(db, user_id, adjustment_data)


@router.delete("/{adjustment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_adjustment_endpoint(
    adjustment_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    delete_adjustment(db, user_id, adjustment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
