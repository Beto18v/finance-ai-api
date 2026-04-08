from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.database.session import get_db
from app.models.obligation import ObligationStatus
from app.schemas.obligation import (
    ObligationCreate,
    ObligationListRead,
    ObligationMarkPaid,
    ObligationPaymentRead,
    ObligationRead,
    ObligationUpcomingRead,
    ObligationUpdate,
)
from app.services.obligation_service import (
    create_obligation,
    delete_obligation,
    get_upcoming_obligations,
    update_obligation,
    list_obligations,
    mark_obligation_paid,
)
from app.services.user_service import ensure_active_user

router = APIRouter(prefix="/obligations", tags=["Obligations"])


@router.post("/", response_model=ObligationRead)
def create_obligation_endpoint(
    obligation_data: ObligationCreate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return create_obligation(db, user_id, obligation_data)


@router.get("/upcoming", response_model=ObligationUpcomingRead)
def get_upcoming_obligations_endpoint(
    user_id=Depends(get_current_user_id),
    days_ahead: int = Query(30, ge=1, le=365),
    limit: int = Query(12, ge=1, le=100),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return get_upcoming_obligations(
        db,
        user_id,
        days_ahead=days_ahead,
        limit=limit,
    )


@router.get("/", response_model=ObligationListRead)
def list_obligations_endpoint(
    user_id=Depends(get_current_user_id),
    status: ObligationStatus | None = Query(None),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return list_obligations(
        db,
        user_id,
        status=status,
    )


@router.patch("/{obligation_id}", response_model=ObligationRead)
def update_obligation_endpoint(
    obligation_id: UUID,
    obligation_data: ObligationUpdate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return update_obligation(db, user_id, obligation_id, obligation_data)


@router.delete("/{obligation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_obligation_endpoint(
    obligation_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    delete_obligation(db, user_id, obligation_id)


@router.post("/{obligation_id}/mark-paid", response_model=ObligationPaymentRead)
def mark_obligation_paid_endpoint(
    obligation_id: UUID,
    payment_data: ObligationMarkPaid,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return mark_obligation_paid(db, user_id, obligation_id, payment_data)
