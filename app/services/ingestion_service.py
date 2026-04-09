from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.finance import assume_utc_if_naive, get_timezone, validate_currency_code
from app.models.category import Category, CategoryDirection
from app.models.ingestion import ImportItem, ImportItemStatus, ImportSession
from app.models.transaction import Transaction, TransactionType
from app.schemas.ingestion import (
    CsvImportCreate,
    ImportCapabilitiesRead,
    ImportSessionAnalysisRead,
    ImportItemUpdate,
    ImportSessionItemRead,
    ImportSessionListItemRead,
    ImportSessionRead,
    ImportSessionSummaryRead,
)
from app.services.financial_account_service import get_financial_account_for_user
from app.services.ledger_shared import (
    PUBLIC_TRANSACTION_TYPES,
    build_ledger_transaction,
    ensure_transaction_amount_is_positive,
    ensure_transaction_currency_matches_financial_account_currency,
    ensure_transaction_currency_matches_user_base_currency,
    resolve_financial_account,
)
from app.services.user_service import ensure_active_user


MAX_IMPORT_ROWS = 1000

DATE_HEADERS = (
    "date",
    "fecha",
    "occurred_at",
    "transaction_date",
    "posted_at",
    "posted_date",
    "booking_date",
    "fecha_operacion",
    "fecha_movimiento",
)
DESCRIPTION_HEADERS = (
    "description",
    "descripcion",
    "details",
    "detail",
    "detalle",
    "memo",
    "merchant",
    "merchant_name",
    "concept",
    "concepto",
    "narrative",
)
CURRENCY_HEADERS = (
    "currency",
    "moneda",
)
CATEGORY_HEADERS = (
    "category",
    "categoria",
)
AMOUNT_HEADERS = (
    "amount",
    "monto",
    "valor",
    "value",
    "importe",
    "total",
)
DEBIT_HEADERS = (
    "debit",
    "debito",
    "withdrawal",
    "charge",
    "cargo",
    "expense",
    "egreso",
    "gasto",
)
CREDIT_HEADERS = (
    "credit",
    "credito",
    "deposit",
    "abono",
    "income",
    "ingreso",
)
TYPE_HEADERS = (
    "type",
    "tipo",
    "direction",
    "movement_type",
    "transaction_type",
    "movimiento",
)

TYPE_ALIASES = {
    "income": TransactionType.income,
    "ingreso": TransactionType.income,
    "credit": TransactionType.income,
    "credito": TransactionType.income,
    "deposit": TransactionType.income,
    "abono": TransactionType.income,
    "in": TransactionType.income,
    "expense": TransactionType.expense,
    "gasto": TransactionType.expense,
    "debit": TransactionType.expense,
    "debito": TransactionType.expense,
    "withdrawal": TransactionType.expense,
    "cargo": TransactionType.expense,
    "out": TransactionType.expense,
}

REQUIRED_IMPORT_FIELDS = {
    "date": DATE_HEADERS,
    "amount": AMOUNT_HEADERS,
    "debit": DEBIT_HEADERS,
    "credit": CREDIT_HEADERS,
}
OPTIONAL_IMPORT_FIELDS = {
    "description": DESCRIPTION_HEADERS,
    "currency": CURRENCY_HEADERS,
    "category": CATEGORY_HEADERS,
    "type": TYPE_HEADERS,
}

DATE_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%m-%d-%Y %H:%M:%S",
    "%m-%d-%Y %H:%M",
)
DATE_ONLY_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%m/%d/%Y",
    "%m-%d-%Y",
)


@dataclass
class ParsedAmount:
    signed_amount: Decimal
    explicit_sign: bool


@dataclass
class ParsedImportRow:
    row_index: int
    raw_row: dict[str, str | None]
    occurred_at: datetime | None
    occurred_on: date | None
    amount: Decimal | None
    currency: str | None
    description: str | None
    normalized_description: str | None
    transaction_type: TransactionType | None
    category_id: UUID | None
    status: ImportItemStatus
    status_reason: str | None


@dataclass
class ParsedImportAnalysis:
    source_headers: list[str]
    detected_columns: dict[str, str]


def get_import_capabilities() -> ImportCapabilitiesRead:
    return ImportCapabilitiesRead(
        max_rows=MAX_IMPORT_ROWS,
        required_fields={
            key: list(value) for key, value in REQUIRED_IMPORT_FIELDS.items()
        },
        optional_fields={
            key: list(value) for key, value in OPTIONAL_IMPORT_FIELDS.items()
        },
        type_aliases=list(TYPE_ALIASES.keys()),
    )


def list_import_sessions(
    db: Session,
    user_id: UUID,
    *,
    limit: int = 5,
) -> list[ImportSessionListItemRead]:
    ensure_active_user(db, user_id)
    sessions = (
        db.query(ImportSession)
        .options(
            joinedload(ImportSession.financial_account),
            selectinload(ImportSession.items),
        )
        .filter(ImportSession.user_id == user_id)
        .order_by(ImportSession.created_at.desc(), ImportSession.id.desc())
        .limit(limit)
        .all()
    )

    return [_serialize_import_session_list_item(session) for session in sessions]


def get_import_session(
    db: Session,
    user_id: UUID,
    import_session_id: UUID,
) -> ImportSessionRead:
    ensure_active_user(db, user_id)
    session = _get_import_session_for_user(
        db,
        user_id,
        import_session_id,
    )
    return _serialize_import_session(session)


def create_csv_import_session(
    db: Session,
    user_id: UUID,
    payload: CsvImportCreate,
) -> ImportSessionRead:
    user = ensure_active_user(db, user_id)
    if not user.base_currency:
        raise HTTPException(
            status_code=409,
            detail="User base currency must be configured before importing CSV",
        )
    if not user.timezone:
        raise HTTPException(
            status_code=409,
            detail="User timezone must be configured before importing CSV",
        )

    financial_account = resolve_financial_account(
        db,
        user_id=user_id,
        user=user,
        financial_account_id=payload.financial_account_id,
    )
    if financial_account.currency is None and user.base_currency is not None:
        financial_account.currency = user.base_currency

    categories = db.query(Category).filter(Category.user_id == user_id).all()
    default_income_category = _resolve_default_category(
        categories,
        payload.default_income_category_id,
        CategoryDirection.income,
        "default income category",
    )
    default_expense_category = _resolve_default_category(
        categories,
        payload.default_expense_category_id,
        CategoryDirection.expense,
        "default expense category",
    )
    categories_by_normalized_name = {
        _normalize_name(category.name): category
        for category in categories
    }

    parsed_rows, parsed_analysis = _parse_csv_import_rows(
        payload.csv_content,
        user_timezone=user.timezone,
        account_currency=financial_account.currency or user.base_currency,
        categories_by_normalized_name=categories_by_normalized_name,
        default_income_category=default_income_category,
        default_expense_category=default_expense_category,
    )

    session = ImportSession(
        user_id=user_id,
        financial_account_id=financial_account.id,
        source_type="csv",
        file_name=payload.file_name,
        analysis_metadata={
            "source_headers": parsed_analysis.source_headers,
            "detected_columns": parsed_analysis.detected_columns,
        },
    )
    db.add(session)
    db.flush()

    for parsed_row in parsed_rows:
        db.add(
            ImportItem(
                import_session_id=session.id,
                user_id=user_id,
                row_index=parsed_row.row_index,
                raw_row=parsed_row.raw_row,
                status=parsed_row.status,
                status_reason=parsed_row.status_reason,
                occurred_at=parsed_row.occurred_at,
                occurred_on=parsed_row.occurred_on,
                amount=parsed_row.amount,
                currency=parsed_row.currency,
                description=parsed_row.description,
                normalized_description=parsed_row.normalized_description,
                transaction_type=parsed_row.transaction_type,
                category_id=parsed_row.category_id,
            )
        )

    db.flush()
    _refresh_import_session_items(
        db,
        user=user,
        session=session,
    )
    db.commit()

    return get_import_session(db, user_id, session.id)


def update_import_item(
    db: Session,
    user_id: UUID,
    import_session_id: UUID,
    item_id: UUID,
    payload: ImportItemUpdate,
) -> ImportSessionRead:
    user = ensure_active_user(db, user_id)
    session = _get_import_session_for_user(
        db,
        user_id,
        import_session_id,
    )
    item = next((current for current in session.items if current.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Import item not found")
    if item.status == ImportItemStatus.imported:
        raise HTTPException(
            status_code=409,
            detail="Imported rows cannot be edited",
        )

    updates = payload.model_dump(exclude_unset=True)
    if "category_id" in updates:
        category_id = updates["category_id"]
        if category_id is None:
            item.category_id = None
            item.category = None
        else:
            category = _get_category_for_user(db, user_id, category_id)
            item.category_id = category.id
            item.category = category

    if updates.get("ignored") is True:
        item.status = ImportItemStatus.ignored
        item.status_reason = "Ignored by user"
    else:
        if updates.get("ignored") is False and item.status == ImportItemStatus.ignored:
            item.status = ImportItemStatus.needs_review
        _refresh_import_session_items(
            db,
            user=user,
            session=session,
        )

    db.commit()
    return get_import_session(db, user_id, session.id)


def commit_import_session(
    db: Session,
    user_id: UUID,
    import_session_id: UUID,
) -> ImportSessionRead:
    user = ensure_active_user(db, user_id)
    session = _get_import_session_for_user(
        db,
        user_id,
        import_session_id,
    )
    financial_account = get_financial_account_for_user(
        db,
        user_id,
        session.financial_account_id,
    )

    _refresh_import_session_items(
        db,
        user=user,
        session=session,
    )

    existing_fingerprints = _build_existing_transaction_fingerprint_map(
        db,
        user_id=user_id,
        financial_account_id=financial_account.id,
        items=session.items,
        user_timezone=user.timezone,
    )

    for item in session.items:
        if item.status != ImportItemStatus.ready:
            continue

        if item.amount is None or item.currency is None or item.occurred_at is None:
            item.status = ImportItemStatus.needs_review
            item.status_reason = "Row is missing required values"
            continue

        category = item.category
        if category is None and item.category_id is not None:
            category = _get_category_for_user(db, user_id, item.category_id)
            item.category = category
        if category is None:
            item.status = ImportItemStatus.needs_review
            item.status_reason = "Category is required before importing"
            continue

        final_transaction_type = _category_direction_to_transaction_type(
            category.direction,
        )
        fingerprint = _build_import_item_fingerprint(
            item=item,
            transaction_type=final_transaction_type,
        )
        if fingerprint is None:
            item.status = ImportItemStatus.needs_review
            item.status_reason = "Row is missing required values"
            continue

        duplicate_transaction = existing_fingerprints.get(fingerprint)
        if duplicate_transaction is not None:
            item.status = ImportItemStatus.duplicate
            item.status_reason = "Matches an existing ledger transaction"
            item.duplicate_transaction_id = duplicate_transaction.id
            item.duplicate_transaction = duplicate_transaction
            continue

        ensure_transaction_amount_is_positive(item.amount)
        ensure_transaction_currency_matches_user_base_currency(
            user_base_currency=user.base_currency,
            transaction_currency=item.currency,
        )
        ensure_transaction_currency_matches_financial_account_currency(
            financial_account=financial_account,
            transaction_currency=item.currency,
        )

        transaction = build_ledger_transaction(
            db,
            user=user,
            financial_account=financial_account,
            transaction_type=final_transaction_type,
            balance_direction=_transaction_type_to_balance_direction(
                final_transaction_type,
            ),
            amount=item.amount,
            currency=item.currency,
            occurred_at=item.occurred_at,
            description=item.description,
            category=category,
        )
        db.add(transaction)
        db.flush()

        item.status = ImportItemStatus.imported
        item.status_reason = "Imported into ledger"
        item.imported_transaction_id = transaction.id
        item.imported_transaction = transaction
        item.duplicate_transaction_id = None
        item.duplicate_transaction = None
        existing_fingerprints[fingerprint] = transaction

    db.commit()
    return get_import_session(db, user_id, session.id)


def _parse_csv_import_rows(
    csv_content: str,
    *,
    user_timezone: str,
    account_currency: str,
    categories_by_normalized_name: dict[str, Category],
    default_income_category: Category | None,
    default_expense_category: Category | None,
) -> tuple[list[ParsedImportRow], ParsedImportAnalysis]:
    normalized_content = csv_content.lstrip("\ufeff")
    dialect = _detect_csv_dialect(normalized_content)
    reader = csv.DictReader(io.StringIO(normalized_content), dialect=dialect)

    if not reader.fieldnames:
        raise HTTPException(status_code=422, detail="CSV header row is required")

    field_map = {
        _normalize_header(field_name): field_name
        for field_name in reader.fieldnames
        if field_name is not None
    }
    date_field = _find_header(field_map, DATE_HEADERS)
    amount_field = _find_header(field_map, AMOUNT_HEADERS)
    debit_field = _find_header(field_map, DEBIT_HEADERS)
    credit_field = _find_header(field_map, CREDIT_HEADERS)
    description_field = _find_header(field_map, DESCRIPTION_HEADERS)
    currency_field = _find_header(field_map, CURRENCY_HEADERS)
    category_field = _find_header(field_map, CATEGORY_HEADERS)
    type_field = _find_header(field_map, TYPE_HEADERS)
    source_headers = [
        field_name.strip()
        for field_name in reader.fieldnames
        if field_name is not None and field_name.strip()
    ]

    if date_field is None:
        raise HTTPException(
            status_code=422,
            detail="CSV must include a recognized date column",
        )
    if amount_field is None and debit_field is None and credit_field is None:
        raise HTTPException(
            status_code=422,
            detail="CSV must include a recognized amount column",
        )

    rows: list[ParsedImportRow] = []
    for row_index, raw_row in enumerate(reader, start=1):
        normalized_row = {
            key.strip(): _normalize_optional_text(value)
            for key, value in (raw_row or {}).items()
            if key is not None
        }
        if not any(value for value in normalized_row.values()):
            continue

        rows.append(
            _parse_csv_row(
                row_index=row_index,
                row=normalized_row,
                date_field=date_field,
                amount_field=amount_field,
                debit_field=debit_field,
                credit_field=credit_field,
                description_field=description_field,
                currency_field=currency_field,
                category_field=category_field,
                type_field=type_field,
                user_timezone=user_timezone,
                account_currency=account_currency,
                categories_by_normalized_name=categories_by_normalized_name,
                default_income_category=default_income_category,
                default_expense_category=default_expense_category,
            )
        )
        if len(rows) > MAX_IMPORT_ROWS:
            raise HTTPException(
                status_code=422,
                detail=f"CSV imports support up to {MAX_IMPORT_ROWS} rows per file",
            )

    if not rows:
        raise HTTPException(status_code=422, detail="CSV contains no data rows")

    return rows, ParsedImportAnalysis(
        source_headers=source_headers,
        detected_columns={
            key: value
            for key, value in {
                "date": date_field,
                "amount": amount_field,
                "debit": debit_field,
                "credit": credit_field,
                "description": description_field,
                "currency": currency_field,
                "category": category_field,
                "type": type_field,
            }.items()
            if value is not None
        },
    )


def _parse_csv_row(
    *,
    row_index: int,
    row: dict[str, str | None],
    date_field: str,
    amount_field: str | None,
    debit_field: str | None,
    credit_field: str | None,
    description_field: str | None,
    currency_field: str | None,
    category_field: str | None,
    type_field: str | None,
    user_timezone: str,
    account_currency: str,
    categories_by_normalized_name: dict[str, Category],
    default_income_category: Category | None,
    default_expense_category: Category | None,
) -> ParsedImportRow:
    description = _normalize_optional_text(
        row.get(description_field) if description_field else None
    )
    normalized_description = _normalize_name(description) if description else None

    occurred_at, occurred_on, date_error = _parse_import_datetime(
        row.get(date_field),
        user_timezone,
    )
    amount, transaction_type, amount_error = _parse_import_amount(
        amount_value=row.get(amount_field) if amount_field else None,
        debit_value=row.get(debit_field) if debit_field else None,
        credit_value=row.get(credit_field) if credit_field else None,
        type_value=row.get(type_field) if type_field else None,
    )

    currency, currency_error = _resolve_row_currency(
        row.get(currency_field) if currency_field else None,
        account_currency,
    )
    if currency is not None and currency != account_currency:
        currency_error = "Currency does not match the selected account"

    matched_category = None
    explicit_category = _normalize_optional_text(
        row.get(category_field) if category_field else None
    )
    if explicit_category:
        matched_category = categories_by_normalized_name.get(
            _normalize_name(explicit_category)
        )

    category_id: UUID | None = None
    if matched_category is not None:
        category_id = matched_category.id
    elif explicit_category is None:
        if transaction_type == TransactionType.income and default_income_category:
            category_id = default_income_category.id
        elif transaction_type == TransactionType.expense and default_expense_category:
            category_id = default_expense_category.id

    status = ImportItemStatus.needs_review
    status_reason = (
        date_error
        or amount_error
        or currency_error
        or (
            f'Category "{explicit_category}" was not found'
            if explicit_category and matched_category is None
            else None
        )
    )
    if status_reason is None:
        status = (
            ImportItemStatus.ready
            if category_id is not None
            else ImportItemStatus.needs_review
        )
        if status == ImportItemStatus.needs_review:
            status_reason = "Category is required before importing"

    return ParsedImportRow(
        row_index=row_index,
        raw_row=row,
        occurred_at=occurred_at,
        occurred_on=occurred_on,
        amount=amount,
        currency=currency,
        description=description,
        normalized_description=normalized_description,
        transaction_type=transaction_type,
        category_id=category_id,
        status=status,
        status_reason=status_reason,
    )


def _refresh_import_session_items(
    db: Session,
    *,
    user,
    session: ImportSession,
) -> None:
    categories_by_id = {
        category.id: category
        for category in db.query(Category).filter(Category.user_id == user.id).all()
    }
    existing_fingerprints = _build_existing_transaction_fingerprint_map(
        db,
        user_id=user.id,
        financial_account_id=session.financial_account_id,
        items=session.items,
        user_timezone=user.timezone,
    )
    seen_fingerprints: set[tuple[str, str, str, str, str]] = set()

    for item in sorted(session.items, key=lambda current: current.row_index):
        if item.status == ImportItemStatus.imported:
            continue
        if item.status == ImportItemStatus.ignored:
            item.status_reason = "Ignored by user"
            continue

        category = categories_by_id.get(item.category_id) if item.category_id else None
        item.category = category
        item.duplicate_transaction_id = None
        item.duplicate_transaction = None

        base_status, base_reason, final_transaction_type = _evaluate_import_item(
            item=item,
            category=category,
            account_currency=session.financial_account.currency
            or user.base_currency,
        )
        if base_status != ImportItemStatus.ready or final_transaction_type is None:
            previous_reason = item.status_reason
            item.status = base_status
            if (
                base_reason == "Category is required before importing"
                and previous_reason
                and "was not found" in previous_reason
            ):
                item.status_reason = previous_reason
            else:
                item.status_reason = base_reason
            continue

        fingerprint = _build_import_item_fingerprint(
            item=item,
            transaction_type=final_transaction_type,
        )
        if fingerprint is None:
            item.status = ImportItemStatus.needs_review
            item.status_reason = "Row is missing required values"
            continue

        duplicate_transaction = existing_fingerprints.get(fingerprint)
        if duplicate_transaction is not None:
            item.status = ImportItemStatus.duplicate
            item.status_reason = "Matches an existing ledger transaction"
            item.duplicate_transaction_id = duplicate_transaction.id
            item.duplicate_transaction = duplicate_transaction
            continue

        if fingerprint in seen_fingerprints:
            item.status = ImportItemStatus.duplicate
            item.status_reason = "Duplicates another row in this import"
            continue

        seen_fingerprints.add(fingerprint)
        item.status = ImportItemStatus.ready
        item.status_reason = None


def _evaluate_import_item(
    *,
    item: ImportItem,
    category: Category | None,
    account_currency: str,
) -> tuple[ImportItemStatus, str | None, TransactionType | None]:
    if item.occurred_at is None or item.occurred_on is None:
        return (
            ImportItemStatus.needs_review,
            "Date could not be parsed",
            None,
        )
    if item.amount is None or item.amount <= 0:
        return (
            ImportItemStatus.needs_review,
            "Amount must be greater than zero",
            None,
        )
    if not item.currency:
        return (
            ImportItemStatus.needs_review,
            "Currency is required",
            None,
        )
    if item.currency != account_currency:
        return (
            ImportItemStatus.needs_review,
            "Currency does not match the selected account",
            None,
        )
    if category is None:
        return (
            ImportItemStatus.needs_review,
            "Category is required before importing",
            None,
        )

    final_transaction_type = _category_direction_to_transaction_type(category.direction)
    if (
        item.transaction_type is not None
        and item.transaction_type != final_transaction_type
    ):
        return (
            ImportItemStatus.needs_review,
            "Category direction conflicts with the imported row",
            None,
        )

    return ImportItemStatus.ready, None, final_transaction_type


def _build_existing_transaction_fingerprint_map(
    db: Session,
    *,
    user_id: UUID,
    financial_account_id: UUID,
    items: list[ImportItem],
    user_timezone: str | None,
) -> dict[tuple[str, str, str, str, str], Transaction]:
    candidate_dates = [item.occurred_at for item in items if item.occurred_at is not None]
    if not candidate_dates:
        return {}

    min_occurred_at = min(candidate_dates) - timedelta(days=1)
    max_occurred_at = max(candidate_dates) + timedelta(days=1)
    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.financial_account_id == financial_account_id,
            Transaction.transaction_type.in_(PUBLIC_TRANSACTION_TYPES),
            Transaction.occurred_at >= min_occurred_at,
            Transaction.occurred_at <= max_occurred_at,
        )
        .all()
    )

    timezone = get_timezone(user_timezone)
    fingerprints: dict[tuple[str, str, str, str, str], Transaction] = {}
    for transaction in transactions:
        occurred_at = assume_utc_if_naive(transaction.occurred_at)
        occurred_on = occurred_at.astimezone(timezone).date()
        fingerprint = (
            transaction.transaction_type.value,
            str(_normalize_decimal(transaction.amount)),
            transaction.currency,
            occurred_on.isoformat(),
            _normalize_name(transaction.description) if transaction.description else "",
        )
        fingerprints.setdefault(fingerprint, transaction)

    return fingerprints


def _build_import_item_fingerprint(
    *,
    item: ImportItem,
    transaction_type: TransactionType,
) -> tuple[str, str, str, str, str] | None:
    if item.amount is None or item.currency is None or item.occurred_on is None:
        return None

    return (
        transaction_type.value,
        str(_normalize_decimal(item.amount)),
        item.currency,
        item.occurred_on.isoformat(),
        item.normalized_description or "",
    )


def _serialize_import_session(session: ImportSession) -> ImportSessionRead:
    return ImportSessionRead(
        id=session.id,
        source_type=session.source_type,
        file_name=session.file_name,
        financial_account_id=session.financial_account_id,
        financial_account_name=session.financial_account.name
        if session.financial_account is not None
        else None,
        analysis=_serialize_import_session_analysis(session.analysis_metadata),
        created_at=session.created_at,
        summary=_build_import_session_summary(session.items),
        items=[
            ImportSessionItemRead(
                id=item.id,
                row_index=item.row_index,
                raw_row=item.raw_row,
                status=item.status,
                status_reason=item.status_reason,
                occurred_at=item.occurred_at,
                occurred_on=item.occurred_on,
                amount=_normalize_decimal(item.amount) if item.amount is not None else None,
                currency=item.currency,
                description=item.description,
                transaction_type=item.transaction_type,
                category_id=item.category_id,
                category_name=item.category.name if item.category is not None else None,
                duplicate_transaction=item.duplicate_transaction,
                imported_transaction=item.imported_transaction,
            )
            for item in session.items
        ],
    )


def _serialize_import_session_analysis(
    analysis_metadata: dict[str, object] | None,
) -> ImportSessionAnalysisRead | None:
    if not analysis_metadata:
        return None

    source_headers = analysis_metadata.get("source_headers")
    detected_columns = analysis_metadata.get("detected_columns")
    if not isinstance(source_headers, list) or not isinstance(detected_columns, dict):
        return None

    return ImportSessionAnalysisRead(
        source_headers=[
            str(header) for header in source_headers if str(header).strip()
        ],
        detected_columns={
            str(key): str(value)
            for key, value in detected_columns.items()
            if str(key).strip() and str(value).strip()
        },
    )


def _serialize_import_session_list_item(
    session: ImportSession,
) -> ImportSessionListItemRead:
    return ImportSessionListItemRead(
        id=session.id,
        source_type=session.source_type,
        file_name=session.file_name,
        financial_account_id=session.financial_account_id,
        financial_account_name=session.financial_account.name
        if session.financial_account is not None
        else None,
        created_at=session.created_at,
        summary=_build_import_session_summary(session.items),
    )


def _build_import_session_summary(
    items: list[ImportItem],
) -> ImportSessionSummaryRead:
    return ImportSessionSummaryRead(
        total_rows=len(items),
        ready_count=sum(item.status == ImportItemStatus.ready for item in items),
        needs_review_count=sum(
            item.status == ImportItemStatus.needs_review for item in items
        ),
        duplicate_count=sum(item.status == ImportItemStatus.duplicate for item in items),
        ignored_count=sum(item.status == ImportItemStatus.ignored for item in items),
        imported_count=sum(item.status == ImportItemStatus.imported for item in items),
    )


def _get_import_session_for_user(
    db: Session,
    user_id: UUID,
    import_session_id: UUID,
) -> ImportSession:
    session = (
        db.query(ImportSession)
        .options(
            joinedload(ImportSession.financial_account),
            selectinload(ImportSession.items).joinedload(ImportItem.category),
            selectinload(ImportSession.items).joinedload(
                ImportItem.duplicate_transaction
            ),
            selectinload(ImportSession.items).joinedload(
                ImportItem.imported_transaction
            ),
        )
        .filter(
            ImportSession.id == import_session_id,
            ImportSession.user_id == user_id,
        )
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Import session not found")
    return session


def _get_category_for_user(
    db: Session,
    user_id: UUID,
    category_id: UUID,
) -> Category:
    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == user_id)
        .first()
    )
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


def _resolve_default_category(
    categories: list[Category],
    category_id: UUID | None,
    direction: CategoryDirection,
    label: str,
) -> Category | None:
    if category_id is None:
        return None

    category = next((item for item in categories if item.id == category_id), None)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if category.direction != direction:
        raise HTTPException(
            status_code=409,
            detail=f"The {label} must use the {direction.value} direction",
        )
    return category


def _detect_csv_dialect(csv_content: str) -> csv.Dialect:
    sample = csv_content[:4096]
    sniffer = csv.Sniffer()
    try:
        return sniffer.sniff(sample, delimiters=",;\t|")
    except csv.Error:
        delimiter = max(
            [",", ";", "\t", "|"],
            key=lambda value: sample.count(value),
        )
        dialect = csv.excel()
        dialect.delimiter = delimiter
        return dialect


def _find_header(
    field_map: dict[str, str],
    aliases: set[str],
) -> str | None:
    for alias in aliases:
        if alias in field_map:
            return field_map[alias]
    return None


def _normalize_header(value: str) -> str:
    return _normalize_name(value.replace("-", "_"))


def _parse_import_datetime(
    value: str | None,
    timezone_name: str,
) -> tuple[datetime | None, date | None, str | None]:
    cleaned = _normalize_optional_text(value)
    if cleaned is None:
        return None, None, "Date is required"

    timezone = get_timezone(timezone_name)
    iso_candidate = cleaned.replace("Z", "+00:00")

    try:
        parsed = datetime.fromisoformat(iso_candidate)
    except ValueError:
        parsed = None

    if parsed is not None:
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            localized = parsed.replace(tzinfo=timezone)
        else:
            localized = parsed.astimezone(timezone)
        return localized, localized.date(), None

    for fmt in DATE_TIME_FORMATS:
        try:
            parsed_datetime = datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
        localized = parsed_datetime.replace(tzinfo=timezone)
        return localized, localized.date(), None

    for fmt in DATE_ONLY_FORMATS:
        try:
            parsed_date = datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
        localized = datetime.combine(parsed_date, time(0, 0), tzinfo=timezone)
        return localized, parsed_date, None

    return None, None, "Date could not be parsed"


def _parse_import_amount(
    *,
    amount_value: str | None,
    debit_value: str | None,
    credit_value: str | None,
    type_value: str | None,
) -> tuple[Decimal | None, TransactionType | None, str | None]:
    parsed_credit = _parse_amount_value(credit_value)
    parsed_debit = _parse_amount_value(debit_value)
    inferred_type = _parse_transaction_type(type_value)

    if parsed_credit is not None and parsed_debit is not None:
        return None, None, "Row contains both debit and credit values"
    if parsed_credit is not None:
        return (
            _normalize_decimal(abs(parsed_credit.signed_amount)),
            TransactionType.income,
            None,
        )
    if parsed_debit is not None:
        return (
            _normalize_decimal(abs(parsed_debit.signed_amount)),
            TransactionType.expense,
            None,
        )

    parsed_amount = _parse_amount_value(amount_value)
    if parsed_amount is None:
        return None, None, "Amount could not be parsed"

    signed_amount = parsed_amount.signed_amount
    if signed_amount == 0:
        return None, None, "Amount must be greater than zero"
    if signed_amount < 0:
        if inferred_type is not None and inferred_type != TransactionType.expense:
            return None, None, "Amount sign conflicts with the row direction"
        return _normalize_decimal(abs(signed_amount)), TransactionType.expense, None
    if parsed_amount.explicit_sign and signed_amount > 0:
        if inferred_type is not None and inferred_type != TransactionType.income:
            return None, None, "Amount sign conflicts with the row direction"
        return _normalize_decimal(signed_amount), TransactionType.income, None

    return _normalize_decimal(signed_amount), inferred_type, None


def _parse_amount_value(value: str | None) -> ParsedAmount | None:
    cleaned = _normalize_optional_text(value)
    if cleaned is None:
        return None

    explicit_negative = cleaned.startswith("-") or (
        cleaned.startswith("(") and cleaned.endswith(")")
    )
    explicit_positive = cleaned.startswith("+")
    numeric = cleaned.strip("()")
    numeric = re.sub(r"[^\d,.\-+]", "", numeric)
    numeric = numeric.lstrip("+")
    if explicit_negative:
        numeric = numeric.lstrip("-")

    if not numeric:
        return None

    if "," in numeric and "." in numeric:
        if numeric.rfind(",") > numeric.rfind("."):
            numeric = numeric.replace(".", "").replace(",", ".")
        else:
            numeric = numeric.replace(",", "")
    elif "," in numeric:
        decimal_part = numeric.rsplit(",", 1)[1]
        if len(decimal_part) <= 2:
            numeric = numeric.replace(".", "").replace(",", ".")
        else:
            numeric = numeric.replace(",", "")
    elif "." in numeric:
        decimal_part = numeric.rsplit(".", 1)[1]
        if len(decimal_part) > 2:
            numeric = numeric.replace(".", "")

    try:
        parsed = Decimal(numeric)
    except InvalidOperation:
        return None

    if explicit_negative:
        parsed = -abs(parsed)
    elif explicit_positive:
        parsed = abs(parsed)

    return ParsedAmount(
        signed_amount=parsed,
        explicit_sign=explicit_negative or explicit_positive,
    )


def _parse_transaction_type(value: str | None) -> TransactionType | None:
    cleaned = _normalize_name(value) if value else None
    if not cleaned:
        return None

    return TYPE_ALIASES.get(cleaned)


def _resolve_row_currency(
    row_currency: str | None,
    account_currency: str,
) -> tuple[str | None, str | None]:
    try:
        normalized_currency = validate_currency_code(row_currency)
    except ValueError:
        return None, "Currency could not be parsed"

    return normalized_currency or account_currency, None


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = " ".join(str(value).split())
    return normalized or None


def _normalize_name(value: str | None) -> str:
    if not value:
        return ""

    ascii_value = unicodedata.normalize("NFKD", value)
    ascii_value = ascii_value.encode("ascii", "ignore").decode("ascii")
    normalized = " ".join(ascii_value.lower().split())
    return normalized


def _category_direction_to_transaction_type(
    direction: CategoryDirection,
) -> TransactionType:
    if direction == CategoryDirection.income:
        return TransactionType.income
    return TransactionType.expense


def _transaction_type_to_balance_direction(
    transaction_type: TransactionType,
):
    from app.models.transaction import BalanceDirection

    if transaction_type == TransactionType.income:
        return BalanceDirection.inflow
    return BalanceDirection.outflow


def _normalize_decimal(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))
