from datetime import datetime, timezone
from uuid import UUID

from app.models.transaction import Transaction


def create_configured_user(client, *, timezone_name: str = "UTC"):
    response = client.post(
        "/users/",
        json={
            "name": "Test User",
            "email": "test@example.com",
            "base_currency": "COP",
            "timezone": timezone_name,
        },
    )
    assert response.status_code == 200
    return response.json()


def create_category(client, *, name: str, direction: str) -> dict:
    response = client.post(
        "/categories/",
        json={"name": name, "direction": direction, "parent_id": None},
    )
    assert response.status_code == 200
    return response.json()


def create_transaction(
    client,
    *,
    category_id: str,
    amount: str,
    description: str,
    occurred_at: datetime,
):
    response = client.post(
        "/transactions/",
        json={
            "category_id": category_id,
            "amount": amount,
            "currency": "COP",
            "description": description,
            "occurred_at": occurred_at.isoformat(),
        },
    )
    assert response.status_code == 200
    return response.json()


def test_category_breakdown_returns_month_totals_percentages_and_skipped_transactions(
    client,
    db_session,
):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    user = create_configured_user(client)
    groceries = create_category(client, name="Groceries", direction="expense")
    rent = create_category(client, name="Rent", direction="expense")
    salary = create_category(client, name="Salary", direction="income")

    create_transaction(
        client,
        category_id=groceries["id"],
        amount="300000.00",
        description="Weekly groceries",
        occurred_at=datetime(2026, 3, 2, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        category_id=groceries["id"],
        amount="200000.00",
        description="Second groceries",
        occurred_at=datetime(2026, 3, 12, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        category_id=rent["id"],
        amount="800000.00",
        description="Monthly rent",
        occurred_at=datetime(2026, 3, 4, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        category_id=salary["id"],
        amount="2500000.00",
        description="Salary",
        occurred_at=datetime(2026, 3, 1, 12, tzinfo=timezone.utc),
    )

    db_session.add(
        Transaction(
            user_id=UUID(user["id"]),
            category_id=UUID(rent["id"]),
            amount="999.00",
            currency="USD",
            base_currency=None,
            amount_in_base_currency=None,
            description="Legacy skipped expense",
            occurred_at=datetime(2026, 3, 7, 12, tzinfo=timezone.utc),
            created_at=datetime(2026, 3, 7, 12, tzinfo=timezone.utc),
        )
    )
    db_session.add(
        Transaction(
            user_id=UUID(user["id"]),
            category_id=UUID(salary["id"]),
            amount="500.00",
            currency="USD",
            base_currency=None,
            amount_in_base_currency=None,
            description="Legacy skipped income",
            occurred_at=datetime(2026, 3, 8, 12, tzinfo=timezone.utc),
            created_at=datetime(2026, 3, 8, 12, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    response = client.get(
        "/analytics/category-breakdown?year=2026&month=3&direction=expense"
    )
    assert response.status_code == 200
    assert response.json() == {
        "month_start": "2026-03-01",
        "currency": "COP",
        "direction": "expense",
        "total": "1300000.00",
        "skipped_transactions": 1,
        "breakdown": [
            {
                "category_id": rent["id"],
                "category_name": "Rent",
                "direction": "expense",
                "amount": "800000.00",
                "percentage": "61.54",
                "transaction_count": 1,
            },
            {
                "category_id": groceries["id"],
                "category_name": "Groceries",
                "direction": "expense",
                "amount": "500000.00",
                "percentage": "38.46",
                "transaction_count": 2,
            },
        ],
    }


def test_category_breakdown_without_direction_includes_all_month_categories(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    create_configured_user(client)
    groceries = create_category(client, name="Groceries", direction="expense")
    salary = create_category(client, name="Salary", direction="income")

    create_transaction(
        client,
        category_id=groceries["id"],
        amount="400000.00",
        description="Groceries",
        occurred_at=datetime(2026, 3, 5, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        category_id=salary["id"],
        amount="1600000.00",
        description="Salary",
        occurred_at=datetime(2026, 3, 8, 12, tzinfo=timezone.utc),
    )

    response = client.get("/analytics/category-breakdown?year=2026&month=3")
    assert response.status_code == 200
    assert response.json() == {
        "month_start": "2026-03-01",
        "currency": "COP",
        "direction": None,
        "total": "2000000.00",
        "skipped_transactions": 0,
        "breakdown": [
            {
                "category_id": salary["id"],
                "category_name": "Salary",
                "direction": "income",
                "amount": "1600000.00",
                "percentage": "80.00",
                "transaction_count": 1,
            },
            {
                "category_id": groceries["id"],
                "category_name": "Groceries",
                "direction": "expense",
                "amount": "400000.00",
                "percentage": "20.00",
                "transaction_count": 1,
            },
        ],
    }


def test_category_breakdown_uses_user_timezone_for_month_boundaries(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    create_configured_user(client, timezone_name="America/Bogota")
    groceries = create_category(client, name="Groceries", direction="expense")

    create_transaction(
        client,
        category_id=groceries["id"],
        amount="300000.00",
        description="Late night groceries",
        occurred_at=datetime(2026, 3, 1, 2, 30, tzinfo=timezone.utc),
    )

    february = client.get(
        "/analytics/category-breakdown?year=2026&month=2&direction=expense"
    )
    assert february.status_code == 200
    assert february.json() == {
        "month_start": "2026-02-01",
        "currency": "COP",
        "direction": "expense",
        "total": "300000.00",
        "skipped_transactions": 0,
        "breakdown": [
            {
                "category_id": groceries["id"],
                "category_name": "Groceries",
                "direction": "expense",
                "amount": "300000.00",
                "percentage": "100.00",
                "transaction_count": 1,
            }
        ],
    }

    march = client.get(
        "/analytics/category-breakdown?year=2026&month=3&direction=expense"
    )
    assert march.status_code == 200
    assert march.json() == {
        "month_start": "2026-03-01",
        "currency": "COP",
        "direction": "expense",
        "total": "0.00",
        "skipped_transactions": 0,
        "breakdown": [],
    }
