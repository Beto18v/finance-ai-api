from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.user import User
from app.models.category import Category
from app.models.transaction import Transaction
from app.schemas.user import UserCreate, UserUpdate


def create_user(db: Session, user_id: UUID, user_data: UserCreate) -> User:
    user: User | None = db.query(User).filter(User.id == user_id).first()
    if user:
        if user.deleted_at is not None:
            user.deleted_at = None
        user.name = user_data.name
        user.email = str(user_data.email)
        db.commit()
        db.refresh(user)
        return user

    user = User(
        id=user_id,
        name=user_data.name,
        email=str(user_data.email),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_current_active_user_from_claims(
    db: Session,
    user_id: UUID,
    claims: dict[str, Any],
) -> User:
    user: User | None = db.query(User).filter(User.id == user_id).first()
    if not user or user.deleted_at is not None:
        raise HTTPException(status_code=404, detail="User not found")

    email = claims.get("email")
    changed = False

    if isinstance(email, str) and user.email != email:
        user.email = email
        changed = True

    if changed:
        db.commit()
        db.refresh(user)

    return user


def ensure_active_user(db: Session, user_id: UUID) -> User:
    user: User | None = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def update_current_user(db: Session, user_id: UUID, user_data: UserUpdate) -> User:
    user: User | None = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updated_fields: dict[str, Any] = user_data.model_dump(exclude_unset=True)
    if "name" in updated_fields and isinstance(updated_fields["name"], str):
        user.name = updated_fields["name"]
    if "email" in updated_fields and updated_fields["email"] is not None:
        user.email = str(updated_fields["email"])

    db.commit()
    db.refresh(user)
    return user


def soft_delete_current_user(db: Session, user_id: UUID) -> None:
    user: User | None = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Delete all user-owned data regardless of amount.
    _ = db.query(Transaction).filter(Transaction.user_id == user_id).delete(synchronize_session=False)
    _ = db.query(Category).filter(Category.user_id == user_id).delete(synchronize_session=False)
    user.deleted_at = datetime.now(timezone.utc)
    db.commit()
