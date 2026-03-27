import uuid

from sqlalchemy import (
    Column,
    ForeignKey,
    String,
    Numeric,
    DateTime,
    Date,
    func,
    Index,
    Uuid,
)

from sqlalchemy.orm import relationship
from app.database.base import Base


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

    fx_rate = Column(
        Numeric(18, 8),
        nullable=True
    )

    fx_rate_date = Column(
        Date,
        nullable=True
    )

    fx_rate_source = Column(
        String(64),
        nullable=True
    )

    base_currency = Column(
        String(3),
        nullable=True
    )

    amount_in_base_currency = Column(
        Numeric(14, 2),
        nullable=True
    )

    description = Column(String)

    occurred_at = Column(
        DateTime(timezone=True),
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
