from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class BalanceMonthRead(BaseModel):
    month_start: date
    income: Decimal
    expense: Decimal
    balance: Decimal


class BalanceOverviewRead(BaseModel):
    current: BalanceMonthRead
    series: list[BalanceMonthRead]