from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_claims, get_current_user_id
from app.database.session import get_db
from app.schemas.user import UserBootstrap, UserCreate, UserRead, UserUpdate
from app.services.user_service import (
    bootstrap_current_user,
    create_user,
    get_current_active_user_from_claims,
    soft_delete_current_user,
    update_current_user,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/", response_model=UserRead)
def create_user_endpoint(
    user_data: UserCreate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return create_user(db, user_id, user_data)


@router.get("/me", response_model=UserRead)
def get_me_endpoint(
    user_id=Depends(get_current_user_id),
    claims: dict = Depends(get_current_user_claims),
    db: Session = Depends(get_db),
):
    return get_current_active_user_from_claims(db, user_id, claims)


@router.post("/me/bootstrap", response_model=UserRead)
def bootstrap_me_endpoint(
    user_data: UserBootstrap | None = None,
    user_id=Depends(get_current_user_id),
    claims: dict = Depends(get_current_user_claims),
    db: Session = Depends(get_db),
):
    return bootstrap_current_user(db, user_id, claims, user_data)


@router.put("/me", response_model=UserRead)
def update_me_endpoint(
    user_data: UserUpdate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return update_current_user(db, user_id, user_data)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me_endpoint(
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    soft_delete_current_user(db, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
