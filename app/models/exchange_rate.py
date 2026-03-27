import uuid

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)

from app.database.base import Base


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    base_currency = Column(
        String(3),
        nullable=False,
    )

    quote_currency = Column(
        String(3),
        nullable=False,
    )

    rate_date = Column(
        Date,
        nullable=False,
    )

    rate = Column(
        Numeric(18, 8),
        nullable=False,
    )

    source = Column(
        String(64),
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "base_currency",
            "quote_currency",
            "rate_date",
            "source",
            name="uq_exchange_rates_pair_date_source",
        ),
        Index(
            "idx_exchange_rates_lookup",
            "base_currency",
            "quote_currency",
            "rate_date",
        ),
    )
