from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.finance import IDENTITY_RATE_SOURCE
from app.models.exchange_rate import ExchangeRate
from app.models.transaction import Transaction
from app.models.user import User

FX_LOOKBACK_DAYS = 7
RATE_QUANTIZER = Decimal("0.00000001")
MONEY_QUANTIZER = Decimal("0.01")


@dataclass(slots=True)
class ResolvedExchangeRate:
    rate: Decimal
    rate_date: date
    source: str


@dataclass(slots=True)
class TransactionFxSnapshot:
    base_currency: str
    fx_rate: Decimal | None
    fx_rate_date: date | None
    fx_rate_source: str | None
    amount_in_base_currency: Decimal | None


def require_user_base_currency(user: User) -> str:
    if not user.base_currency:
        raise HTTPException(
            status_code=409,
            detail="User base currency must be configured before calculating analytics or transactions",
        )

    return user.base_currency


def resolve_transaction_fx_snapshot(
    db: Session,
    *,
    user: User,
    transaction_currency: str,
    occurred_at: datetime,
    amount: Decimal,
) -> TransactionFxSnapshot:
    base_currency = require_user_base_currency(user)
    rate_date = occurred_at.date()

    if transaction_currency == base_currency:
        normalized_amount = _normalize_money(amount)
        return TransactionFxSnapshot(
            base_currency=base_currency,
            fx_rate=Decimal("1").quantize(RATE_QUANTIZER),
            fx_rate_date=rate_date,
            fx_rate_source=IDENTITY_RATE_SOURCE,
            amount_in_base_currency=normalized_amount,
        )

    resolved_rate = resolve_exchange_rate(
        db,
        source_currency=transaction_currency,
        target_currency=base_currency,
        target_date=rate_date,
    )

    if not resolved_rate:
        return TransactionFxSnapshot(
            base_currency=base_currency,
            fx_rate=None,
            fx_rate_date=None,
            fx_rate_source=None,
            amount_in_base_currency=None,
        )

    return TransactionFxSnapshot(
        base_currency=base_currency,
        fx_rate=resolved_rate.rate,
        fx_rate_date=resolved_rate.rate_date,
        fx_rate_source=resolved_rate.source,
        amount_in_base_currency=_normalize_money(amount * resolved_rate.rate),
    )


def apply_transaction_fx_snapshot(
    transaction: Transaction,
    snapshot: TransactionFxSnapshot,
) -> None:
    transaction.base_currency = snapshot.base_currency
    transaction.fx_rate = snapshot.fx_rate
    transaction.fx_rate_date = snapshot.fx_rate_date
    transaction.fx_rate_source = snapshot.fx_rate_source
    transaction.amount_in_base_currency = snapshot.amount_in_base_currency


def refresh_transaction_fx_snapshots_for_user(db: Session, user: User) -> None:
    if not user.base_currency:
        return

    transactions = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.occurred_at.asc())
        .all()
    )

    for transaction in transactions:
        snapshot = resolve_transaction_fx_snapshot(
            db,
            user=user,
            transaction_currency=transaction.currency,
            occurred_at=transaction.occurred_at,
            amount=transaction.amount,
        )
        apply_transaction_fx_snapshot(transaction, snapshot)


def resolve_exchange_rate(
    db: Session,
    *,
    source_currency: str,
    target_currency: str,
    target_date: date,
) -> ResolvedExchangeRate | None:
    direct_rate = _find_latest_rate(
        db,
        base_currency=source_currency,
        quote_currency=target_currency,
        target_date=target_date,
    )
    if direct_rate:
        return ResolvedExchangeRate(
            rate=_normalize_rate(direct_rate.rate),
            rate_date=direct_rate.rate_date,
            source=direct_rate.source,
        )

    inverse_rate = _find_latest_rate(
        db,
        base_currency=target_currency,
        quote_currency=source_currency,
        target_date=target_date,
    )
    if not inverse_rate or Decimal(inverse_rate.rate) == 0:
        return None

    return ResolvedExchangeRate(
        rate=_normalize_rate(Decimal("1") / Decimal(inverse_rate.rate)),
        rate_date=inverse_rate.rate_date,
        source=f"{inverse_rate.source}:inverse",
    )


def _find_latest_rate(
    db: Session,
    *,
    base_currency: str,
    quote_currency: str,
    target_date: date,
) -> ExchangeRate | None:
    minimum_date = target_date - timedelta(days=FX_LOOKBACK_DAYS)

    return (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.base_currency == base_currency,
            ExchangeRate.quote_currency == quote_currency,
            ExchangeRate.rate_date <= target_date,
            ExchangeRate.rate_date >= minimum_date,
        )
        .order_by(ExchangeRate.rate_date.desc(), ExchangeRate.created_at.desc())
        .first()
    )


def _normalize_rate(value: Decimal | int | float) -> Decimal:
    return Decimal(str(value)).quantize(RATE_QUANTIZER, rounding=ROUND_HALF_UP)


def _normalize_money(value: Decimal | int | float) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
