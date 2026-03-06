from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.auth import get_current_user_id

from app.database.session import get_db
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.services.category_service import (
    create_category,
    delete_category,
    get_category,
    get_user_categories,
    update_category,
)

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.post("/", response_model=CategoryRead)
def create_category_endpoint(
    category_data: CategoryCreate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    return create_category(db, user_id, category_data)


@router.get("/", response_model=list[CategoryRead])
def get_categories_endpoint(
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    return get_user_categories(db, user_id)


@router.get("/{category_id}", response_model=CategoryRead)
def get_category_endpoint(
    category_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return get_category(db, user_id, category_id)


@router.put("/{category_id}", response_model=CategoryRead)
def update_category_endpoint(
    category_id: UUID,
    category_data: CategoryUpdate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return update_category(db, user_id, category_id, category_data)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category_endpoint(
    category_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    delete_category(db, user_id, category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)