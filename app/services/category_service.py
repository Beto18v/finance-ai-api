from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.category import Category
from app.models.transaction import Transaction
from app.schemas.category import CategoryCreate, CategoryUpdate


def normalize_category_name(name: str) -> str:
    return " ".join(name.split())


def ensure_unique_category_name(
    db: Session,
    user_id: UUID,
    name: str,
    exclude_category_id: UUID | None = None,
) -> str:
    normalized_name = normalize_category_name(name)

    existing_category_query = db.query(Category).filter(
        Category.user_id == user_id,
        func.lower(func.trim(Category.name)) == normalized_name.lower(),
    )

    if exclude_category_id is not None:
        existing_category_query = existing_category_query.filter(
            Category.id != exclude_category_id
        )

    if existing_category_query.first():
        raise HTTPException(status_code=409, detail="Category already exists")

    return normalized_name


def ensure_parent_category_can_group(
    db: Session,
    user_id: UUID,
    parent_id: UUID,
    direction,
) -> Category:
    parent = db.query(Category).filter(
        Category.id == parent_id,
        Category.user_id == user_id,
    ).first()

    if not parent:
        raise HTTPException(status_code=404, detail="Parent category not found")

    if parent.parent_id is not None:
        raise HTTPException(
            status_code=409,
            detail="Parent category must be top-level",
        )

    if parent.direction != direction:
        raise HTTPException(
            status_code=409,
            detail="Parent category must have same direction",
        )

    return parent


def category_has_children(db: Session, category_id: UUID) -> bool:
    return (
        db.query(Category)
        .filter(Category.parent_id == category_id)
        .first()
        is not None
    )


def category_has_transactions(db: Session, category_id: UUID) -> bool:
    return (
        db.query(Transaction.id)
        .filter(Transaction.category_id == category_id)
        .limit(1)
        .first()
        is not None
    )


def create_category(
    db: Session,
    user_id: UUID,
    category_data: CategoryCreate,
):
    normalized_name = ensure_unique_category_name(db, user_id, category_data.name)

    if category_data.parent_id is not None:
        ensure_parent_category_can_group(
            db,
            user_id,
            category_data.parent_id,
            category_data.direction,
        )

    category = Category(
        user_id=user_id,
        name=normalized_name,
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
    resulting_direction = updates.get("direction", category.direction)
    has_children = category_has_children(db, category.id)

    if "name" in updates:
        updates["name"] = ensure_unique_category_name(
            db,
            user_id,
            updates["name"],
            exclude_category_id=category.id,
        )

    if "parent_id" in updates:
        if updates["parent_id"] == category.id:
            raise HTTPException(status_code=400, detail="Category cannot be its own parent")

        if updates["parent_id"] is not None and has_children:
            raise HTTPException(
                status_code=409,
                detail="Category already acts as a group",
            )

    if has_children and "direction" in updates and updates["direction"] != category.direction:
        raise HTTPException(
            status_code=409,
            detail="Group direction cannot change while it has subcategories",
        )

    effective_parent_id = updates.get("parent_id", category.parent_id)

    if effective_parent_id is not None:
        ensure_parent_category_can_group(
            db,
            user_id,
            effective_parent_id,
            resulting_direction,
        )

    for field, value in updates.items():
        setattr(category, field, value)

    db.commit()
    db.refresh(category)
    return category


def delete_category(db: Session, user_id: UUID, category_id: UUID) -> None:
    category = get_category(db, user_id, category_id)

    if category_has_children(db, category.id):
        raise HTTPException(status_code=409, detail="Category has subcategories")

    if category_has_transactions(db, category.id):
        raise HTTPException(status_code=409, detail="Category has transactions")

    db.delete(category)
    db.commit()
