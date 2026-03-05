import uuid

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Uuid,
    func
)

from sqlalchemy.orm import relationship
from app.database.base import Base


class User(Base):
    __tablename__ = "users"

    # Primary key
    id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # User information
    name = Column(
        String,
        nullable=False
    )

    # User email, unique and indexed for faster lookups
    email = Column(
        String,
        unique=True,
        nullable=False,
        index=True
    )

    # Timestamps for record management
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # Timestamp for when the record was last updated, automatically set on update
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now()
    )

    # Timestamp for soft deletion, nullable to indicate active records
    deleted_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

## Relationships
    # One-to-many relationship with transactions, back_populates to allow bidirectional access
    transactions = relationship(
        "Transaction",
        back_populates="user"
    )
    # One-to-many relationship with categories, back_populates to allow bidirectional access
    categories = relationship(
        "Category",
        back_populates="user"
    )