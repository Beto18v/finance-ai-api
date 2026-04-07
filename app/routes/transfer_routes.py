from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.database.session import get_db
from app.schemas.ledger import TransferCreate, TransferRead
from app.services.transfer_service import create_transfer, delete_transfer
from app.services.user_service import ensure_active_user

router = APIRouter(prefix="/transfers", tags=["Transfers"])


@router.post("/", response_model=TransferRead)
def create_transfer_endpoint(
    transfer_data: TransferCreate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return create_transfer(db, user_id, transfer_data)


@router.delete("/{transfer_group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transfer_endpoint(
    transfer_group_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    delete_transfer(db, user_id, transfer_group_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
