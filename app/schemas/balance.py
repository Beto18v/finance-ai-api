from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class BalanceMonthRead(BaseModel):
    month_start: date
    currency: str | None = None
    income: Decimal
    expense: Decimal
    balance: Decimal
    skipped_transactions: int = 0


class BalanceOverviewRead(BaseModel):
    currency: str | None = None
    current: BalanceMonthRead
    series: list[BalanceMonthRead]
