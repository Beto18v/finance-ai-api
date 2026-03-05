from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id

from app.database.session import get_db
from app.schemas.category import CategoryCreate, CategoryRead
from app.services.category_service import create_category, get_user_categories

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