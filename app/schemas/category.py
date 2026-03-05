from uuid import UUID
from datetime import datetime
from pydantic import BaseModel
from pydantic import ConfigDict
from app.models.category import CategoryDirection


class CategoryCreate(BaseModel):
    name: str
    direction: CategoryDirection
    parent_id: UUID | None = None


class CategoryRead(BaseModel):
    id: UUID
    name: str
    direction: CategoryDirection
    parent_id: UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)