from __future__ import annotations

import argparse
import json
import os
import random
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib import error, request


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_COUNT = 100
DEFAULT_DAYS_BACK = 90
DEFAULT_TIMEOUT = 20.0


EXPENSE_DEFAULT_CATEGORIES = [
    "Groceries",
    "Dining Out",
    "Transport",
    "Utilities",
    "Health",
    "Shopping",
    "Entertainment",
]

INCOME_DEFAULT_CATEGORIES = [
    "Salary",
    "Freelance",
    "Bonus",
]

EXPENSE_DESCRIPTION_TEMPLATES = [
    "Weekly market",
    "Coffee and snacks",
    "Cab ride",
    "Monthly bill",
    "Pharmacy order",
    "Streaming night",
    "Online purchase",
    "Home supplies",
]

INCOME_DESCRIPTION_TEMPLATES = [
    "Monthly salary",
    "Freelance payment",
    "Project advance",
    "Bonus payout",
    "Refund received",
]


class ApiClientError(RuntimeError):
    pass


@dataclass(slots=True)
class Category:
    id: str
    name: str
    direction: str
    parent_id: str | None


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    token = (args.access_token or os.getenv("DINERANCE_ACCESS_TOKEN") or "").strip()
    if not token:
        parser.error(
            "Missing access token. Pass --access-token or set DINERANCE_ACCESS_TOKEN."
        )

    rng = random.Random(args.seed)
    base_url = normalize_base_url(args.base_url)

    try:
        profile = get_or_bootstrap_profile(
            base_url=base_url,
            token=token,
            timeout=args.timeout,
        )
        base_currency = str(profile.get("base_currency") or "").strip().upper()
        if not base_currency:
            raise ApiClientError(
                "User base_currency is missing. Configure it first in Dinerance before seeding transactions."
            )

        categories = ensure_seed_categories(
            base_url=base_url,
            token=token,
            timeout=args.timeout,
        )
        created = create_random_transactions(
            base_url=base_url,
            token=token,
            timeout=args.timeout,
            categories=categories,
            base_currency=base_currency,
            count=args.count,
            days_back=args.days_back,
            rng=rng,
        )
    except ApiClientError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Created {created} transactions for {profile.get('email')} in {base_currency} "
        f"against {base_url}."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed random Dinerance transactions through the public API.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API base URL. Default: {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--access-token",
        default="",
        help="Supabase access token. If omitted, reads DINERANCE_ACCESS_TOKEN.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help=f"Number of transactions to create. Default: {DEFAULT_COUNT}",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=DEFAULT_DAYS_BACK,
        help=f"Spread transactions across the last N days. Default: {DEFAULT_DAYS_BACK}",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for reproducible output.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds. Default: {DEFAULT_TIMEOUT}",
    )
    return parser


def normalize_base_url(base_url: str) -> str:
    candidate = base_url.strip()
    if not candidate.startswith(("http://", "https://")):
        candidate = f"http://{candidate}"
    return candidate.rstrip("/")


def get_or_bootstrap_profile(*, base_url: str, token: str, timeout: float) -> dict[str, Any]:
    try:
        return api_request(
            "GET",
            "/users/me",
            base_url=base_url,
            token=token,
            timeout=timeout,
        )
    except ApiClientError as exc:
        if "404" not in str(exc):
            raise

    return api_request(
        "POST",
        "/users/me/bootstrap",
        base_url=base_url,
        token=token,
        timeout=timeout,
    )


def ensure_seed_categories(
    *,
    base_url: str,
    token: str,
    timeout: float,
) -> list[Category]:
    categories = parse_categories(
        api_request(
            "GET",
            "/categories/",
            base_url=base_url,
            token=token,
            timeout=timeout,
        )
    )

    desired_by_direction = {
        "expense": EXPENSE_DEFAULT_CATEGORIES,
        "income": INCOME_DEFAULT_CATEGORIES,
    }
    existing_names = {
        normalize_category_name(category.name): category
        for category in categories
    }

    for direction, desired_names in desired_by_direction.items():
        for name in desired_names:
            normalized_name = normalize_category_name(name)
            if normalized_name in existing_names:
                continue

            created = api_request(
                "POST",
                "/categories/",
                base_url=base_url,
                token=token,
                timeout=timeout,
                payload={
                    "name": name,
                    "direction": direction,
                    "parent_id": None,
                },
            )
            category = to_category(created)
            categories.append(category)
            existing_names[normalized_name] = category

    expense_count = sum(1 for category in categories if category.direction == "expense")
    income_count = sum(1 for category in categories if category.direction == "income")
    if expense_count == 0 or income_count == 0:
        raise ApiClientError(
            "Could not ensure both income and expense categories for seeding."
        )

    return categories


def parse_categories(payload: Any) -> list[Category]:
    if not isinstance(payload, list):
        raise ApiClientError("Unexpected categories payload.")
    return [to_category(item) for item in payload]


def to_category(payload: Any) -> Category:
    if not isinstance(payload, dict):
        raise ApiClientError("Unexpected category payload.")
    return Category(
        id=str(payload["id"]),
        name=str(payload["name"]),
        direction=str(payload["direction"]),
        parent_id=str(payload["parent_id"]) if payload.get("parent_id") else None,
    )


def normalize_category_name(value: str) -> str:
    return " ".join(value.split()).strip().lower()


def create_random_transactions(
    *,
    base_url: str,
    token: str,
    timeout: float,
    categories: list[Category],
    base_currency: str,
    count: int,
    days_back: int,
    rng: random.Random,
) -> int:
    if count <= 0:
        raise ApiClientError("--count must be greater than zero.")
    if days_back <= 0:
        raise ApiClientError("--days-back must be greater than zero.")

    expenses = [category for category in categories if category.direction == "expense"]
    incomes = [category for category in categories if category.direction == "income"]

    created = 0
    for index in range(count):
        direction = "income" if rng.random() < 0.2 else "expense"
        category = rng.choice(incomes if direction == "income" else expenses)
        occurred_at = random_datetime_within_days(days_back=days_back, rng=rng)
        amount = random_amount(currency=base_currency, direction=direction, rng=rng)
        description = random_description(
            direction=direction,
            category_name=category.name,
            rng=rng,
        )

        api_request(
            "POST",
            "/transactions/",
            base_url=base_url,
            token=token,
            timeout=timeout,
            payload={
                "category_id": category.id,
                "amount": format_decimal(amount),
                "currency": base_currency,
                "description": description,
                "occurred_at": occurred_at.isoformat().replace("+00:00", "Z"),
            },
        )
        created += 1

        if created % 10 == 0 or created == count:
            print(f"Created {created}/{count} transactions...")

    return created


def random_datetime_within_days(*, days_back: int, rng: random.Random) -> datetime:
    now = datetime.now(UTC)
    start = now - timedelta(days=days_back)
    total_seconds = int((now - start).total_seconds())
    return start + timedelta(seconds=rng.randint(0, total_seconds))


def random_amount(*, currency: str, direction: str, rng: random.Random) -> Decimal:
    ranges = {
        "USD": {"expense": (6, 240), "income": (350, 4200)},
        "EUR": {"expense": (6, 220), "income": (300, 3800)},
        "COP": {"expense": (12000, 480000), "income": (650000, 6200000)},
        "MXN": {"expense": (90, 2800), "income": (2500, 42000)},
        "PEN": {"expense": (18, 680), "income": (900, 12000)},
        "BRL": {"expense": (20, 900), "income": (1200, 17000)},
        "CLP": {"expense": (7000, 240000), "income": (450000, 4200000)},
        "ARS": {"expense": (8000, 320000), "income": (250000, 4200000)},
    }
    fallback = {"expense": (8, 300), "income": (500, 5000)}
    selected = ranges.get(currency.upper(), fallback)[direction]

    amount = Decimal(str(rng.uniform(*selected)))
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def random_description(*, direction: str, category_name: str, rng: random.Random) -> str:
    templates = (
        INCOME_DESCRIPTION_TEMPLATES
        if direction == "income"
        else EXPENSE_DESCRIPTION_TEMPLATES
    )
    return f"{rng.choice(templates)} - {category_name}"


def format_decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def api_request(
    method: str,
    path: str,
    *,
    base_url: str,
    token: str,
    timeout: float,
    payload: dict[str, Any] | None = None,
) -> Any:
    url = f"{base_url}{path}"
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return parse_response(response)
    except error.HTTPError as exc:
        detail = parse_http_error(exc)
        raise ApiClientError(f"{exc.code} {method} {path}: {detail}") from exc
    except error.URLError as exc:
        raise ApiClientError(f"Could not reach {url}: {exc.reason}") from exc


def parse_response(response: Any) -> Any:
    body = response.read()
    if not body:
        return None
    charset = response.headers.get_content_charset() or "utf-8"
    return json.loads(body.decode(charset))


def parse_http_error(exc: error.HTTPError) -> str:
    raw_body = exc.read()
    if raw_body:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
            if isinstance(payload, dict) and payload.get("detail"):
                return str(payload["detail"])
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass

    return exc.reason or "Request failed"


if __name__ == "__main__":
    raise SystemExit(main())
