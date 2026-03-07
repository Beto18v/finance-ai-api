from uuid import UUID

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


def create_category(
    db: Session,
    user_id: UUID,
    category_data: CategoryCreate,
):

    if category_data.parent_id is not None:
        parent = db.query(Category).filter(
            Category.id == category_data.parent_id,
            Category.user_id == user_id,
        ).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent category not found")

    category = Category(
        user_id=user_id,
        name=category_data.name,
        direction=category_data.direction,
        parent_id=category_data.parent_id
    )

    db.add(category)
    db.commit()
    db.refresh(category)

    return category


def get_category(db: Session, user_id: UUID, category_id: UUID) -> Category:
    category = db.query(Category).filter(
        Category.id == category_id,
        Category.user_id == user_id,
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


def get_user_categories(db: Session, user_id: UUID) -> list[Category]:

    return db.query(Category).filter(
        Category.user_id == user_id
    ).all()


def update_category(
    db: Session,
    user_id: UUID,
    category_id: UUID,
    category_data: CategoryUpdate,
):
    category = get_category(db, user_id, category_id)
    updates = category_data.model_dump(exclude_unset=True)

    if "parent_id" in updates and updates["parent_id"] is not None:
        if updates["parent_id"] == category.id:
            raise HTTPException(status_code=400, detail="Category cannot be its own parent")

        parent = db.query(Category).filter(
            Category.id == updates["parent_id"],
            Category.user_id == user_id,
        ).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent category not found")

    for field, value in updates.items():
        setattr(category, field, value)

    db.commit()
    db.refresh(category)
    return category


def delete_category(db: Session, user_id: UUID, category_id: UUID) -> None:
    category = get_category(db, user_id, category_id)
    db.delete(category)
    db.commit()