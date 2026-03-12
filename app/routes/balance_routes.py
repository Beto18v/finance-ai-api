from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.database.session import get_db
from app.schemas.balance import BalanceOverviewRead
from app.services.balance_service import get_balance_overview
from app.services.user_service import ensure_active_user

router = APIRouter(prefix="/balance", tags=["Balance"])


@router.get("/monthly", response_model=BalanceOverviewRead)
def get_monthly_balance_endpoint(
    year: int | None = Query(None, ge=1900, le=9999),
    month: int | None = Query(None, ge=1, le=12),
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return get_balance_overview(db, user_id, year=year, month=month)