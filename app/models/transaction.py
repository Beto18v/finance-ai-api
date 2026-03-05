import uuid
import enum

from sqlalchemy import (
    Column,
    ForeignKey,
    String,
    Numeric,
    DateTime,
    Enum,
    func,
    Index,
    Uuid,
)

from sqlalchemy.orm import relationship
from app.database.base import Base


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    posted = "posted"


class Transaction(Base):
    __tablename__ = "transactions"

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

    category_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("categories.id"),
        nullable=False
    )

    amount = Column(
        Numeric(12, 2),
        nullable=False
    )

    currency = Column(
        String(3),
        default="COP",
        nullable=False
    )

    description = Column(String)

    merchant_name = Column(String)

    occurred_at = Column(
        DateTime(timezone=True),
        nullable=False
    )

    status = Column(
        Enum(TransactionStatus),
        default=TransactionStatus.posted,
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now()
    )

    ## Relationships
    user = relationship("User", back_populates="transactions")

    category = relationship("Category", back_populates="transactions")

    __table_args__ = (
        Index("idx_user_date", "user_id", "occurred_at"),
        Index("idx_user_category", "user_id", "category_id"),
    )