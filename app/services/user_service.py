from sqlalchemy.orm import Session
from app.models.user import User
import uuid


def get_user_by_email(db: Session, email: str):

    return db.query(User).filter(
        User.email == email,
        User.deleted_at.is_(None)
    ).first()


def get_or_create_user_from_claims(db: Session, user_id: uuid.UUID, claims: dict) -> User:
    email = claims.get("email")

    user = db.query(User).filter(User.id == user_id).first()
    if user:
        if email and user.email != email:
            user.email = email
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