import uuid
import enum

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Enum,
    ForeignKey,
    Uuid,
    func
)

from sqlalchemy.orm import relationship
from app.database.base import Base


class CategoryDirection(str, enum.Enum):
    income = "income"
    expense = "expense"


class Category(Base):
    __tablename__ = "categories"

    id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False
    )

    name = Column(
        String,
        nullable=False
    )

    direction = Column(
        Enum(CategoryDirection),
        nullable=False
    )

    parent_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("categories.id"),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

## Relationships
    user = relationship(
        "User",
        back_populates="categories"
    )

    # Subcategorías
    children = relationship(
        "Category",
        backref="parent",
        remote_side=[id]
    )

    transactions = relationship(
        "Transaction",
        back_populates="category"
    )

    obligations = relationship(
        "Obligation",
        back_populates="category"
    )
