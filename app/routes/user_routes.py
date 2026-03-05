from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_claims, get_current_user_id
from app.database.session import get_db
from app.schemas.user import UserRead
from app.services.user_service import get_or_create_user_from_claims

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserRead)
def get_me_endpoint(
    user_id=Depends(get_current_user_id),
    claims: dict = Depends(get_current_user_claims),
    db: Session = Depends(get_db),
):
    return get_or_create_user_from_claims(db, user_id, claims)