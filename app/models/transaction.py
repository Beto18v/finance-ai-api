import uuid
import enum

from sqlalchemy import (
    Column,
    CheckConstraint,
    ForeignKey,
    String,
    Numeric,
    DateTime,
    Date,
    Enum,
    func,
    Index,
    Uuid,
)

from sqlalchemy.orm import relationship
from app.database.base import Base


class TransactionType(str, enum.Enum):
    income = "income"
    expense = "expense"
    transfer = "transfer"
    adjustment = "adjustment"


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

    financial_account_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("financial_accounts.id"),
        nullable=False
    )

    category_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("categories.id"),
        nullable=True
    )

    transaction_type = Column(
        Enum(TransactionType),
        nullable=False
    )

    transfer_group_id = Column(
        Uuid(as_uuid=True),
        nullable=True
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

    financial_account = relationship(
        "FinancialAccount",
        back_populates="transactions"
    )

    category = relationship("Category", back_populates="transactions")

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        Index("idx_user_date", "user_id", "occurred_at"),
        Index("idx_user_category", "user_id", "category_id"),
        Index(
            "idx_transactions_user_financial_account",
            "user_id",
            "financial_account_id",
        ),
        Index("idx_transactions_transfer_group", "transfer_group_id"),
    )
