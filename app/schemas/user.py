from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, EmailStr
from pydantic import ConfigDict
from pydantic import field_validator

from app.core.finance import (
    assume_utc_if_naive,
    normalize_timezone_name,
    validate_currency_code,
)


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    base_currency: str | None = None
    timezone: str | None = None

    @field_validator("base_currency", mode="before")
    @classmethod
    def validate_base_currency(cls, value: str | None) -> str | None:
        return validate_currency_code(value)

    @field_validator("timezone", mode="before")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        return normalize_timezone_name(value)


class UserUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    base_currency: str | None = None
    timezone: str | None = None

    @field_validator("base_currency", mode="before")
    @classmethod
    def validate_base_currency(cls, value: str | None) -> str | None:
        return validate_currency_code(value)

    @field_validator("timezone", mode="before")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        return normalize_timezone_name(value)


class UserBootstrap(BaseModel):
    name: str | None = None
    base_currency: str | None = None
    timezone: str | None = None

    @field_validator("base_currency", mode="before")
    @classmethod
    def validate_base_currency(cls, value: str | None) -> str | None:
        return validate_currency_code(value)

    @field_validator("timezone", mode="before")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        return normalize_timezone_name(value)


class UserRead(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    base_currency: str | None = None
    timezone: str | None = None
    created_at: datetime
    deleted_at: datetime | None = None

    @field_validator("created_at", "deleted_at", mode="before")
    @classmethod
    def validate_response_datetimes(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return assume_utc_if_naive(value)

    model_config = ConfigDict(from_attributes=True)
