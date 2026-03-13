from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, EmailStr
from pydantic import ConfigDict


class UserCreate(BaseModel):
    name: str
    email: EmailStr


class UserUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None


class UserBootstrap(BaseModel):
    name: str | None = None


class UserRead(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    created_at: datetime
    deleted_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
