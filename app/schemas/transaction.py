from uuid import UUID
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from pydantic import ConfigDict
from app.models.transaction import TransactionStatus


class TransactionCreate(BaseModel):
    category_id: UUID
    amount: Decimal
    currency: str = "COP"
    description: str | None = None
    merchant_name: str | None = None
    occurred_at: datetime


class TransactionRead(BaseModel):
    id: UUID
    category_id: UUID
    amount: Decimal
    currency: str
    description: str | None
    merchant_name: str | None
    occurred_at: datetime
    status: TransactionStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)