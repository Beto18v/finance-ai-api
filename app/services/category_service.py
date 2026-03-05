from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.category import Category
from app.schemas.category import CategoryCreate
import uuid


def create_category(
    db: Session,
    user_id,
    category_data: CategoryCreate
):

    if category_data.parent_id is not None:
        parent = db.query(Category).filter(
            Category.id == category_data.parent_id,
            Category.user_id == user_id,
        ).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent category not found")

    category = Category(
        id=uuid.uuid4(),
        user_id=user_id,
        name=category_data.name,
        direction=category_data.direction,
        parent_id=category_data.parent_id
    )

    db.add(category)
    db.commit()
    db.refresh(category)

    return category


def get_user_categories(db: Session, user_id):

    return db.query(Category).filter(
        Category.user_id == user_id
    ).all()