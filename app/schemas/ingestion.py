from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.finance import assume_utc_if_naive, validate_currency_code
from app.models.ingestion import ImportItemStatus
from app.models.transaction import TransactionType
from app.schemas.transaction import TransactionRead


def _normalize_required_text(value: str, field_name: str) -> str:
    normalized = " ".join(str(value).split())
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


class CsvImportCreate(BaseModel):
    file_name: str
    csv_content: str
    financial_account_id: UUID | None = None
    default_income_category_id: UUID | None = None
    default_expense_category_id: UUID | None = None

    @field_validator("file_name", mode="before")
    @classmethod
    def validate_file_name(cls, value: str) -> str:
        return _normalize_required_text(value, "File name")

    @field_validator("csv_content", mode="before")
    @classmethod
    def validate_csv_content(cls, value: str) -> str:
        normalized = str(value)
        if not normalized.strip():
            raise ValueError("CSV content is required")
        return normalized


class ImportItemUpdate(BaseModel):
    category_id: UUID | None = None
    ignored: bool | None = None


class ImportSessionSummaryRead(BaseModel):
    total_rows: int
    ready_count: int
    needs_review_count: int
    duplicate_count: int
    ignored_count: int
    imported_count: int


class ImportSessionAnalysisRead(BaseModel):
    source_headers: list[str]
    detected_columns: dict[str, str]


class ImportCapabilitiesRead(BaseModel):
    max_rows: int
    required_fields: dict[str, list[str]]
    optional_fields: dict[str, list[str]]
    type_aliases: list[str]


class ImportSessionItemRead(BaseModel):
    id: UUID
    row_index: int
    raw_row: dict[str, str | None]
    status: ImportItemStatus
    status_reason: str | None = None
    occurred_at: datetime | None = None
    occurred_on: date | None = None
    amount: Decimal | None = None
    currency: str | None = None
    description: str | None = None
    transaction_type: TransactionType | None = None
    category_id: UUID | None = None
    category_name: str | None = None
    duplicate_transaction: TransactionRead | None = None
    imported_transaction: TransactionRead | None = None

    @field_validator("currency", mode="before")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        return validate_currency_code(value)

    @field_validator("occurred_at", mode="before")
    @classmethod
    def validate_occurred_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return assume_utc_if_naive(value)

    model_config = ConfigDict(from_attributes=True)


class ImportSessionRead(BaseModel):
    id: UUID
    source_type: str
    file_name: str
    financial_account_id: UUID
    financial_account_name: str | None = None
    analysis: ImportSessionAnalysisRead | None = None
    created_at: datetime
    summary: ImportSessionSummaryRead
    items: list[ImportSessionItemRead]

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return assume_utc_if_naive(value)


class ImportSessionListItemRead(BaseModel):
    id: UUID
    source_type: str
    file_name: str
    financial_account_id: UUID
    financial_account_name: str | None = None
    created_at: datetime
    summary: ImportSessionSummaryRead

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return assume_utc_if_naive(value)
