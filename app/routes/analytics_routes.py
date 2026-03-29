from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.database.session import get_db
from app.schemas.analytics import AnalyticsSummaryRead
from app.services.analytics_service import get_analytics_summary
from app.services.user_service import ensure_active_user

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary", response_model=AnalyticsSummaryRead)
def get_analytics_summary_endpoint(
    year: int | None = Query(None, ge=1900, le=9999),
    month: int | None = Query(None, ge=1, le=12),
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return get_analytics_summary(db, user_id, year=year, month=month)
