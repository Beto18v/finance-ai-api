from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.obligation import Obligation, ObligationStatus
from app.schemas.cashflow import (
    CashflowForecastRead,
    ForecastWindowRead,
    SafeToSpendRead,
)
from app.services.ledger_service import get_ledger_balances
from app.services.obligation_schedule import advance_due_date
from app.services.obligation_service import resolve_obligation_reference_date
from app.services.user_service import ensure_active_user

FORECAST_HORIZON_DAYS = (30, 60, 90)
DEFAULT_SAFE_TO_SPEND_HORIZON_DAYS = 30


@dataclass(frozen=True)
class ScheduledPayment:
    obligation_id: UUID
    due_date: date
    amount: Decimal


def get_cashflow_forecast(
    db: Session,
    user_id: UUID,
    *,
    reference_date: date | None = None,
) -> CashflowForecastRead:
    currency, current_balance, resolved_reference_date = _load_cashflow_inputs(
        db,
        user_id,
        reference_date=reference_date,
    )
    scheduled_payments = _expand_scheduled_payments(
        db,
        user_id,
        window_end_date=_window_end_date(
            resolved_reference_date,
            FORECAST_HORIZON_DAYS[-1],
        ),
    )

    horizons = [
        _build_forecast_window(
            current_balance=current_balance,
            reference_date=resolved_reference_date,
            horizon_days=horizon_days,
            scheduled_payments=scheduled_payments,
        )
        for horizon_days in FORECAST_HORIZON_DAYS
    ]
    safe_to_spend = _serialize_safe_to_spend(
        currency=currency,
        current_balance=current_balance,
        reference_date=resolved_reference_date,
        window=horizons[0],
    )

    return CashflowForecastRead(
        reference_date=resolved_reference_date,
        currency=currency,
        current_balance=current_balance,
        safe_to_spend=safe_to_spend,
        horizons=horizons,
    )


def get_safe_to_spend(
    db: Session,
    user_id: UUID,
    *,
    horizon_days: int = DEFAULT_SAFE_TO_SPEND_HORIZON_DAYS,
    reference_date: date | None = None,
) -> SafeToSpendRead:
    currency, current_balance, resolved_reference_date = _load_cashflow_inputs(
        db,
        user_id,
        reference_date=reference_date,
    )
    if horizon_days < 1:
        raise HTTPException(
            status_code=422,
            detail="Safe-to-spend horizon must be at least 1 day",
        )

    scheduled_payments = _expand_scheduled_payments(
        db,
        user_id,
        window_end_date=_window_end_date(resolved_reference_date, horizon_days),
    )
    window = _build_forecast_window(
        current_balance=current_balance,
        reference_date=resolved_reference_date,
        horizon_days=horizon_days,
        scheduled_payments=scheduled_payments,
    )
    return _serialize_safe_to_spend(
        currency=currency,
        current_balance=current_balance,
        reference_date=resolved_reference_date,
        window=window,
    )


def _load_cashflow_inputs(
    db: Session,
    user_id: UUID,
    *,
    reference_date: date | None,
) -> tuple[str, Decimal, date]:
    user = ensure_active_user(db, user_id)
    if not user.base_currency:
        raise HTTPException(
            status_code=409,
            detail="User base currency must be configured before calculating forecast",
        )

    ledger_balances = get_ledger_balances(db, user_id)
    resolved_reference_date = reference_date or resolve_obligation_reference_date(
        user.timezone
    )
    return (
        ledger_balances.currency or user.base_currency,
        _normalize_decimal(ledger_balances.consolidated_balance),
        resolved_reference_date,
    )


def _expand_scheduled_payments(
    db: Session,
    user_id: UUID,
    *,
    window_end_date: date,
) -> list[ScheduledPayment]:
    obligations = (
        db.query(Obligation)
        .filter(
            Obligation.user_id == user_id,
            Obligation.status == ObligationStatus.active,
            Obligation.next_due_date <= window_end_date,
        )
        .order_by(
            Obligation.next_due_date.asc(),
            Obligation.created_at.asc(),
            Obligation.id.asc(),
        )
        .all()
    )

    scheduled_payments: list[ScheduledPayment] = []
    for obligation in obligations:
        due_date = obligation.next_due_date
        while due_date <= window_end_date:
            scheduled_payments.append(
                ScheduledPayment(
                    obligation_id=obligation.id,
                    due_date=due_date,
                    amount=_normalize_decimal(obligation.amount),
                )
            )
            due_date = advance_due_date(
                cadence=obligation.cadence,
                due_date=due_date,
                monthly_anchor_day=obligation.monthly_anchor_day,
                monthly_anchor_is_month_end=obligation.monthly_anchor_is_month_end,
            )

    scheduled_payments.sort(key=lambda item: (item.due_date, item.obligation_id))
    return scheduled_payments


def _build_forecast_window(
    *,
    current_balance: Decimal,
    reference_date: date,
    horizon_days: int,
    scheduled_payments: list[ScheduledPayment],
) -> ForecastWindowRead:
    window_end_date = _window_end_date(reference_date, horizon_days)
    payments_in_window = [
        payment for payment in scheduled_payments if payment.due_date <= window_end_date
    ]
    confirmed_obligations_total = sum(
        (payment.amount for payment in payments_in_window),
        start=Decimal("0.00"),
    )
    projected_balance = _normalize_decimal(current_balance - confirmed_obligations_total)
    safe_to_spend = _normalize_decimal(max(projected_balance, Decimal("0.00")))
    shortfall_amount = _normalize_decimal(max(-projected_balance, Decimal("0.00")))

    return ForecastWindowRead(
        horizon_days=horizon_days,
        window_end_date=window_end_date,
        scheduled_payments_count=len(payments_in_window),
        confirmed_obligations_total=_normalize_decimal(confirmed_obligations_total),
        projected_balance=projected_balance,
        safe_to_spend=safe_to_spend,
        safe_to_spend_per_day=_normalize_decimal(safe_to_spend / Decimal(horizon_days)),
        shortfall_amount=shortfall_amount,
        status=_resolve_window_status(projected_balance),
    )


def _serialize_safe_to_spend(
    *,
    currency: str,
    current_balance: Decimal,
    reference_date: date,
    window: ForecastWindowRead,
) -> SafeToSpendRead:
    return SafeToSpendRead(
        reference_date=reference_date,
        horizon_days=window.horizon_days,
        window_end_date=window.window_end_date,
        currency=currency,
        current_balance=current_balance,
        scheduled_payments_count=window.scheduled_payments_count,
        confirmed_obligations_total=window.confirmed_obligations_total,
        projected_balance=window.projected_balance,
        safe_to_spend=window.safe_to_spend,
        safe_to_spend_per_day=window.safe_to_spend_per_day,
        shortfall_amount=window.shortfall_amount,
        status=window.status,
    )


def _window_end_date(reference_date: date, horizon_days: int) -> date:
    return reference_date.fromordinal(reference_date.toordinal() + horizon_days)


def _resolve_window_status(
    projected_balance: Decimal,
) -> str:
    if projected_balance < 0:
        return "shortfall"
    if projected_balance == 0:
        return "tight"
    return "covered"


def _normalize_decimal(value: Decimal | int | float | None) -> Decimal:
    if value is None:
        return Decimal("0.00")

    if isinstance(value, Decimal):
        normalized = value
    else:
        normalized = Decimal(str(value))

    return normalized.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
