from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.core.finance import assume_utc_if_naive
from app.schemas.balance import BalanceOverviewRead


class AnalyticsSummaryTransactionRead(BaseModel):
    id: UUID
    category_id: UUID
    category_name: str
    direction: str
    amount: Decimal
    currency: str
    base_currency: str | None = None
    amount_in_base_currency: Decimal | None = None
    description: str | None = None
    occurred_at: datetime

    @field_validator("occurred_at", mode="before")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        return assume_utc_if_naive(value)


class AnalyticsSummaryRead(BalanceOverviewRead):
    recent_transactions: list[AnalyticsSummaryTransactionRead]
