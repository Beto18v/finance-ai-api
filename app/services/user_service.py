from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from datetime import datetime, timezone
import uuid


def get_user_by_email(db: Session, email: str):

    return db.query(User).filter(
        User.email == email,
        User.deleted_at.is_(None)
    ).first()


def create_user(db: Session, user_id: uuid.UUID, user_data: UserCreate) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        if user.deleted_at is not None:
            user.deleted_at = None
        user.name = user_data.name
        user.email = str(user_data.email)
        db.add(user)
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


def get_or_create_user_from_claims(db: Session, user_id: uuid.UUID, claims: dict) -> User:
    email = claims.get("email")

    user = db.query(User).filter(User.id == user_id).first()
    if user:
        changed = False

        # If the user comes back after account deletion, re-activate profile.
        if user.deleted_at is not None:
            user.deleted_at = None
            changed = True

        if email and user.email != email:
            user.email = email
            changed = True

        if changed:
            db.add(user)
            db.commit()
            db.refresh(user)

        return user

    # Create a minimal profile row mapped to the Supabase Auth user id
    user = User(
        id=user_id,
        name=claims.get("user_metadata", {}).get("full_name")
        or claims.get("user_metadata", {}).get("name")
        or claims.get("email")
        or "User",
        email=email or f"{user_id}@local.invalid",
    )

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_current_user(db: Session, user_id: uuid.UUID, user_data: UserUpdate) -> User:
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updated_fields = user_data.model_dump(exclude_unset=True)
    if "name" in updated_fields:
        user.name = updated_fields["name"]
    if "email" in updated_fields and updated_fields["email"] is not None:
        user.email = str(updated_fields["email"])

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def soft_delete_current_user(db: Session, user_id: uuid.UUID) -> None:
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.deleted_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()