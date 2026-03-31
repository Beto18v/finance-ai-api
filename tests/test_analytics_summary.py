from datetime import datetime, timezone
from uuid import UUID

from app.models.financial_account import FinancialAccount
from app.models.transaction import Transaction
from app.models.transaction import TransactionType


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
    financial_account_id: str | None = None,
):
    response = client.post(
        "/transactions/",
        json={
            "category_id": category_id,
            "financial_account_id": financial_account_id,
            "amount": amount,
            "currency": "COP",
            "description": description,
            "occurred_at": occurred_at.isoformat(),
        },
    )
    assert response.status_code == 200
    return response.json()


def test_analytics_summary_wraps_monthly_balance_and_recent_transactions(
    client,
    db_session,
):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    user = create_configured_user(client)
    income_category = create_category(client, name="Salary", direction="income")
    expense_category = create_category(client, name="Bills", direction="expense")

    create_transaction(
        client,
        category_id=income_category["id"],
        amount="1800000.00",
        description="January salary",
        occurred_at=datetime(2026, 1, 15, 12, tzinfo=timezone.utc),
    )

    create_transaction(
        client,
        category_id=income_category["id"],
        amount="2500000.00",
        description="Salary",
        occurred_at=datetime(2026, 3, 1, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        category_id=expense_category["id"],
        amount="1200000.00",
        description="Rent",
        occurred_at=datetime(2026, 3, 3, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        category_id=expense_category["id"],
        amount="150000.00",
        description="Groceries",
        occurred_at=datetime(2026, 3, 5, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        category_id=income_category["id"],
        amount="300000.00",
        description="Freelance",
        occurred_at=datetime(2026, 3, 8, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        category_id=expense_category["id"],
        amount="50000.00",
        description="Transport",
        occurred_at=datetime(2026, 3, 10, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        category_id=income_category["id"],
        amount="100000.00",
        description="Bonus",
        occurred_at=datetime(2026, 3, 12, 12, tzinfo=timezone.utc),
    )

    default_account = (
        db_session.query(FinancialAccount)
        .filter(
            FinancialAccount.user_id == UUID(user["id"]),
            FinancialAccount.is_default.is_(True),
        )
        .first()
    )
    assert default_account is not None

    db_session.add(
        Transaction(
            user_id=UUID(user["id"]),
            financial_account_id=default_account.id,
            category_id=UUID(expense_category["id"]),
            transaction_type=TransactionType.expense,
            amount="999.00",
            currency="USD",
            base_currency=None,
            amount_in_base_currency=None,
            description="Legacy skipped",
            occurred_at=datetime(2026, 3, 7, 12, tzinfo=timezone.utc),
            created_at=datetime(2026, 3, 7, 12, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    response = client.get("/analytics/summary")
    assert response.status_code == 200

    data = response.json()
    assert data["current"] == {
        "month_start": "2026-03-01",
        "currency": "COP",
        "income": "2900000.00",
        "expense": "1400000.00",
        "balance": "1500000.00",
        "skipped_transactions": 1,
    }
    assert data["series"] == [
        {
            "month_start": "2026-03-01",
            "currency": "COP",
            "income": "2900000.00",
            "expense": "1400000.00",
            "balance": "1500000.00",
            "skipped_transactions": 1,
        },
        {
            "month_start": "2026-01-01",
            "currency": "COP",
            "income": "1800000.00",
            "expense": "0.00",
            "balance": "1800000.00",
            "skipped_transactions": 0,
        },
    ]

    recent_transactions = data["recent_transactions"]
    assert len(recent_transactions) == 5
    assert [item["description"] for item in recent_transactions] == [
        "Bonus",
        "Transport",
        "Freelance",
        "Legacy skipped",
        "Groceries",
    ]
    assert recent_transactions[0]["category_name"] == "Salary"
    assert recent_transactions[0]["direction"] == "income"
    assert recent_transactions[0]["financial_account_id"] == str(default_account.id)
    assert recent_transactions[3]["currency"] == "USD"
    assert recent_transactions[3]["amount_in_base_currency"] is None


def test_analytics_summary_returns_zeroes_and_no_recent_transactions_for_empty_month(
    client,
):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    create_configured_user(client)

    response = client.get("/analytics/summary?year=2026&month=2")
    assert response.status_code == 200
    assert response.json() == {
        "currency": "COP",
        "current": {
            "month_start": "2026-02-01",
            "currency": "COP",
            "income": "0.00",
            "expense": "0.00",
            "balance": "0.00",
            "skipped_transactions": 0,
        },
        "series": [],
        "recent_transactions": [],
    }


def test_analytics_summary_uses_user_timezone_for_recent_transactions(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    create_configured_user(client, timezone_name="America/Bogota")
    default_account = client.get("/financial-accounts/").json()[0]
    income_category = create_category(client, name="Salary", direction="income")

    create_transaction(
        client,
        category_id=income_category["id"],
        amount="300000.00",
        description="Late night salary",
        occurred_at=datetime(2026, 3, 1, 2, 30, tzinfo=timezone.utc),
    )

    february = client.get("/analytics/summary?year=2026&month=2")
    assert february.status_code == 200
    assert february.json()["current"] == {
        "month_start": "2026-02-01",
        "currency": "COP",
        "income": "300000.00",
        "expense": "0.00",
        "balance": "300000.00",
        "skipped_transactions": 0,
    }
    assert february.json()["recent_transactions"] == [
        {
            "id": february.json()["recent_transactions"][0]["id"],
            "category_id": income_category["id"],
            "financial_account_id": default_account["id"],
            "category_name": "Salary",
            "direction": "income",
            "amount": "300000.00",
            "currency": "COP",
            "base_currency": "COP",
            "amount_in_base_currency": "300000.00",
            "description": "Late night salary",
            "occurred_at": "2026-03-01T02:30:00Z",
        }
    ]

    march = client.get("/analytics/summary?year=2026&month=3")
    assert march.status_code == 200
    assert march.json()["current"] == {
        "month_start": "2026-03-01",
        "currency": "COP",
        "income": "0.00",
        "expense": "0.00",
        "balance": "0.00",
        "skipped_transactions": 0,
    }
    assert march.json()["recent_transactions"] == []


def test_analytics_summary_can_filter_by_financial_account(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    create_configured_user(client)
    income_category = create_category(client, name="Salary", direction="income")
    expense_category = create_category(client, name="Bills", direction="expense")

    default_account = client.get("/financial-accounts/").json()[0]
    extra_account = client.post(
        "/financial-accounts/",
        json={"name": "Wallet"},
    ).json()

    create_transaction(
        client,
        financial_account_id=default_account["id"],
        category_id=income_category["id"],
        amount="100000.00",
        description="Main salary",
        occurred_at=datetime(2026, 3, 1, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        financial_account_id=extra_account["id"],
        category_id=expense_category["id"],
        amount="30000.00",
        description="Wallet bills",
        occurred_at=datetime(2026, 3, 3, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        financial_account_id=extra_account["id"],
        category_id=income_category["id"],
        amount="50000.00",
        description="Wallet salary",
        occurred_at=datetime(2026, 3, 5, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        financial_account_id=default_account["id"],
        category_id=expense_category["id"],
        amount="10000.00",
        description="Main bills",
        occurred_at=datetime(2026, 3, 7, 12, tzinfo=timezone.utc),
    )

    consolidated = client.get("/analytics/summary?year=2026&month=3")
    assert consolidated.status_code == 200
    assert consolidated.json()["current"] == {
        "month_start": "2026-03-01",
        "currency": "COP",
        "income": "150000.00",
        "expense": "40000.00",
        "balance": "110000.00",
        "skipped_transactions": 0,
    }
    assert {
        item["financial_account_id"]
        for item in consolidated.json()["recent_transactions"]
    } == {default_account["id"], extra_account["id"]}

    filtered = client.get(
        f"/analytics/summary?year=2026&month=3&financial_account_id={extra_account['id']}"
    )
    assert filtered.status_code == 200
    assert filtered.json()["current"] == {
        "month_start": "2026-03-01",
        "currency": "COP",
        "income": "50000.00",
        "expense": "30000.00",
        "balance": "20000.00",
        "skipped_transactions": 0,
    }
    assert [item["description"] for item in filtered.json()["recent_transactions"]] == [
        "Wallet salary",
        "Wallet bills",
    ]
    assert {
        item["financial_account_id"] for item in filtered.json()["recent_transactions"]
    } == {extra_account["id"]}
