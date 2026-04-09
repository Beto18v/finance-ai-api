import enum
import uuid

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.transaction import TransactionType


class ImportItemStatus(str, enum.Enum):
    ready = "ready"
    needs_review = "needs_review"
    duplicate = "duplicate"
    ignored = "ignored"
    imported = "imported"


class ImportSession(Base):
    __tablename__ = "import_sessions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    financial_account_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("financial_accounts.id"),
        nullable=False,
    )
    source_type = Column(String(16), nullable=False, default="csv")
    file_name = Column(String, nullable=False)
    analysis_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User")
    financial_account = relationship("FinancialAccount")
    items = relationship(
        "ImportItem",
        back_populates="import_session",
        cascade="all, delete-orphan",
        order_by="ImportItem.row_index",
    )

    __table_args__ = (
        Index("idx_import_sessions_user_created", "user_id", "created_at"),
    )


class ImportItem(Base):
    __tablename__ = "import_items"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    import_session_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("import_sessions.id"),
        nullable=False,
    )
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    row_index = Column(Integer, nullable=False)
    raw_row = Column(JSON, nullable=False)
    status = Column(
        Enum(
            ImportItemStatus,
            values_callable=lambda enum_class: [item.value for item in enum_class],
            name="importitemstatus",
        ),
        nullable=False,
        default=ImportItemStatus.needs_review,
    )
    status_reason = Column(String, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=True)
    occurred_on = Column(Date, nullable=True)
    amount = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(3), nullable=True)
    description = Column(String, nullable=True)
    normalized_description = Column(String, nullable=True)
    transaction_type = Column(
        Enum(TransactionType),
        nullable=True,
    )
    category_id = Column(Uuid(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    duplicate_transaction_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("transactions.id"),
        nullable=True,
    )
    imported_transaction_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("transactions.id"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    import_session = relationship("ImportSession", back_populates="items")
    category = relationship("Category")
    duplicate_transaction = relationship(
        "Transaction",
        foreign_keys=[duplicate_transaction_id],
    )
    imported_transaction = relationship(
        "Transaction",
        foreign_keys=[imported_transaction_id],
    )

    __table_args__ = (
        Index(
            "idx_import_items_session_row",
            "import_session_id",
            "row_index",
            unique=True,
        ),
        Index("idx_import_items_user_status", "user_id", "status"),
    )
