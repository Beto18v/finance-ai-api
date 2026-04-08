from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from app.analytics.common import get_next_month_start, normalize_money
from app.core.finance import assume_utc_if_naive, get_timezone

ANALYSIS_WINDOW_DAYS = 365
MAX_RECURRING_CANDIDATES = 8

CADENCE_PRIORITY = {
    "monthly": 0,
    "biweekly": 1,
    "weekly": 2,
}

DESCRIPTION_MIN_OCCURRENCES = {
    "monthly": 3,
    "biweekly": 3,
    "weekly": 4,
}

CATEGORY_AMOUNT_MIN_OCCURRENCES = {
    "monthly": 3,
    "biweekly": 4,
    "weekly": 5,
}

DESCRIPTION_AMOUNT_RATIO_LIMIT = {
    "monthly": Decimal("1.20"),
    "biweekly": Decimal("1.15"),
    "weekly": Decimal("1.10"),
}


@dataclass(slots=True)
class RecurringCandidateRow:
    transaction_id: UUID
    category_id: UUID
    category_name: str
    occurred_at: datetime
    amount: Decimal
    currency: str
    description: str | None
    direction: str


@dataclass(slots=True)
class RecurringCandidate:
    recurring_candidate_key: str
    label: str
    description: str | None
    category_id: UUID
    category_name: str
    direction: str
    cadence: str
    match_basis: str
    amount_pattern: str
    currency: str
    typical_amount: Decimal
    amount_min: Decimal
    amount_max: Decimal
    occurrence_count: int
    interval_days: list[int]
    first_occurred_at: datetime
    last_occurred_at: datetime


@dataclass(slots=True)
class RecurringCandidatesOverview:
    month_start: date
    history_window_start: date
    candidates: list[RecurringCandidate]


@dataclass(slots=True)
class _PatternPoint:
    transaction_id: UUID
    category_id: UUID
    category_name: str
    occurred_at: datetime
    local_date: date
    amount: Decimal
    currency: str
    description: str | None
    normalized_description: str | None
    direction: str


def build_recurring_candidates(
    rows: list[RecurringCandidateRow],
    *,
    month_start: date,
    timezone_name: str,
) -> RecurringCandidatesOverview:
    timezone_info = get_timezone(timezone_name)
    history_window_start = month_start - timedelta(days=ANALYSIS_WINDOW_DAYS)
    month_end = get_next_month_start(month_start) - timedelta(days=1)

    description_groups: dict[tuple[str, UUID, str, str], list[_PatternPoint]] = {}
    category_amount_groups: dict[tuple[str, UUID, str, str], list[_PatternPoint]] = {}

    for row in rows:
        occurred_at = assume_utc_if_naive(row.occurred_at)
        local_date = occurred_at.astimezone(timezone_info).date()
        normalized_description = _normalize_description(row.description)
        description = _clean_description(row.description)
        point = _PatternPoint(
            transaction_id=row.transaction_id,
            category_id=row.category_id,
            category_name=row.category_name,
            occurred_at=occurred_at,
            local_date=local_date,
            amount=normalize_money(row.amount),
            currency=row.currency,
            description=description,
            normalized_description=normalized_description,
            direction=row.direction,
        )

        if normalized_description:
            description_groups.setdefault(
                (
                    point.direction,
                    point.category_id,
                    point.currency,
                    normalized_description,
                ),
                [],
            ).append(point)
            continue

        category_amount_groups.setdefault(
            (
                point.direction,
                point.category_id,
                point.currency,
                str(point.amount),
            ),
            [],
        ).append(point)

    candidates: list[RecurringCandidate] = []

    for grouped_points in description_groups.values():
        candidate = _build_candidate_from_group(
            grouped_points,
            match_basis="description",
            month_start=month_start,
            month_end=month_end,
        )
        if candidate is not None:
            candidates.append(candidate)

    for grouped_points in category_amount_groups.values():
        candidate = _build_candidate_from_group(
            grouped_points,
            match_basis="category_amount",
            month_start=month_start,
            month_end=month_end,
        )
        if candidate is not None:
            candidates.append(candidate)

    candidates.sort(
        key=lambda item: (
            0 if item.match_basis == "description" else 1,
            -item.last_occurred_at.timestamp(),
            -item.occurrence_count,
            CADENCE_PRIORITY[item.cadence],
            item.label.lower(),
        )
    )

    return RecurringCandidatesOverview(
        month_start=month_start,
        history_window_start=history_window_start,
        candidates=candidates[:MAX_RECURRING_CANDIDATES],
    )


def _build_candidate_from_group(
    points: list[_PatternPoint],
    *,
    match_basis: str,
    month_start: date,
    month_end: date,
) -> RecurringCandidate | None:
    sorted_points = sorted(
        points,
        key=lambda item: (item.local_date, item.occurred_at, str(item.transaction_id)),
    )
    if len(sorted_points) < 2:
        return None

    last_point = sorted_points[-1]
    if last_point.local_date < month_start or last_point.local_date > month_end:
        return None

    best_candidate: RecurringCandidate | None = None

    for cadence in ("monthly", "biweekly", "weekly"):
        streak = _build_recent_streak(sorted_points, cadence)
        if len(streak) < _required_occurrences(match_basis=match_basis, cadence=cadence):
            continue
        if match_basis == "description" and not _amounts_are_stable(
            streak,
            cadence=cadence,
        ):
            continue

        candidate = _serialize_candidate(
            streak,
            cadence=cadence,
            match_basis=match_basis,
        )
        if best_candidate is None or (
            candidate.occurrence_count > best_candidate.occurrence_count
        ):
            best_candidate = candidate

    return best_candidate


def _build_recent_streak(
    points: list[_PatternPoint],
    cadence: str,
) -> list[_PatternPoint]:
    streak = [points[-1]]

    for index in range(len(points) - 2, -1, -1):
        previous = points[index]
        current = streak[0]
        if _matches_cadence(previous, current, cadence):
            streak.insert(0, previous)
            continue
        break

    return streak


def _serialize_candidate(
    streak: list[_PatternPoint],
    *,
    cadence: str,
    match_basis: str,
) -> RecurringCandidate:
    amounts = [item.amount for item in streak]
    total_amount = sum(amounts, start=Decimal("0.00"))
    amount_min = min(amounts)
    amount_max = max(amounts)
    amount_pattern = "exact" if amount_min == amount_max else "stable"
    representative = streak[-1]
    label = representative.description or representative.category_name
    interval_days = _build_interval_days(streak)

    return RecurringCandidate(
        recurring_candidate_key=build_recurring_candidate_key(
            match_basis=match_basis,
            direction=representative.direction,
            category_id=representative.category_id,
            currency=representative.currency,
            normalized_description=representative.normalized_description,
            amount=representative.amount,
        ),
        label=label,
        description=representative.description,
        category_id=representative.category_id,
        category_name=representative.category_name,
        direction=representative.direction,
        cadence=cadence,
        match_basis=match_basis,
        amount_pattern=amount_pattern,
        currency=representative.currency,
        typical_amount=normalize_money(total_amount / Decimal(len(amounts))),
        amount_min=amount_min,
        amount_max=amount_max,
        occurrence_count=len(streak),
        interval_days=interval_days,
        first_occurred_at=streak[0].occurred_at,
        last_occurred_at=streak[-1].occurred_at,
    )


def _build_interval_days(streak: list[_PatternPoint]) -> list[int]:
    return [
        (current.local_date - previous.local_date).days
        for previous, current in zip(streak, streak[1:])
    ]


def _required_occurrences(*, match_basis: str, cadence: str) -> int:
    if match_basis == "description":
        return DESCRIPTION_MIN_OCCURRENCES[cadence]
    return CATEGORY_AMOUNT_MIN_OCCURRENCES[cadence]


def _amounts_are_stable(
    streak: list[_PatternPoint],
    *,
    cadence: str,
) -> bool:
    amounts = [item.amount for item in streak]
    amount_min = min(amounts)
    amount_max = max(amounts)
    if amount_min <= 0:
        return False
    return amount_max <= amount_min * DESCRIPTION_AMOUNT_RATIO_LIMIT[cadence]


def _matches_cadence(
    previous: _PatternPoint,
    current: _PatternPoint,
    cadence: str,
) -> bool:
    if cadence == "monthly":
        return _matches_monthly(previous.local_date, current.local_date)

    day_interval = (current.local_date - previous.local_date).days
    if cadence == "biweekly":
        return 12 <= day_interval <= 16
    if cadence == "weekly":
        return 6 <= day_interval <= 8
    return False


def _matches_monthly(previous_date: date, current_date: date) -> bool:
    if _month_delta(previous_date, current_date) != 1:
        return False

    if abs(previous_date.day - current_date.day) <= 4:
        return True

    return _is_month_end(previous_date) and _is_month_end(current_date)


def _month_delta(previous_date: date, current_date: date) -> int:
    return (current_date.year - previous_date.year) * 12 + (
        current_date.month - previous_date.month
    )


def _is_month_end(value: date) -> bool:
    return value.day == monthrange(value.year, value.month)[1]


def build_recurring_candidate_key(
    *,
    match_basis: str,
    direction: str,
    category_id: UUID,
    currency: str,
    normalized_description: str | None = None,
    amount: Decimal | None = None,
) -> str:
    if match_basis == "description":
        identity_value = normalized_description or ""
    else:
        identity_value = str(normalize_money(amount or Decimal("0.00")))

    raw_key = "|".join(
        (
            "rc_v1",
            match_basis,
            direction,
            str(category_id),
            currency.upper(),
            identity_value,
        )
    )
    return sha256(raw_key.encode("utf-8")).hexdigest()


def _clean_description(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


def _normalize_description(value: str | None) -> str | None:
    cleaned = _clean_description(value)
    if cleaned is None:
        return None
    return cleaned.lower()
