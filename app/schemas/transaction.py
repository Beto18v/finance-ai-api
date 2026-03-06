from uuid import UUID
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from pydantic import ConfigDict


class TransactionCreate(BaseModel):
    category_id: UUID
    amount: Decimal
    currency: str = "COP"
    description: str | None = None
    occurred_at: datetime


class TransactionUpdate(BaseModel):
    category_id: UUID | None = None
    amount: Decimal | None = None
    currency: str | None = None
    description: str | None = None
    occurred_at: datetime | None = None


class TransactionRead(BaseModel):
    id: UUID
    category_id: UUID
    amount: Decimal
    currency: str
    description: str | None
    occurred_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)