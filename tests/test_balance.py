from datetime import datetime, timezone
from uuid import UUID

from app.models.transaction import Transaction, TransactionType


def create_configured_user(client):
    return client.post(
        "/users/",
        json={
            "name": "Test User",
            "email": "test@example.com",
            "base_currency": "COP",
            "timezone": "UTC",
        },
    )


def test_balance_defaults_to_latest_month_with_data(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    create_configured_user(client)

    income_category = client.post(
        "/categories/",
        json={"name": "Salary", "direction": "income", "parent_id": None},
    ).json()
    expense_category = client.post(
        "/categories/",
        json={"name": "Rent", "direction": "expense", "parent_id": None},
    ).json()

    client.post(
        "/transactions/",
        json={
            "category_id": income_category["id"],
            "amount": "2500000.00",
            "currency": "COP",
            "description": "Salary January",
            "occurred_at": datetime(2026, 1, 15, tzinfo=timezone.utc).isoformat(),
        },
    )
    client.post(
        "/transactions/",
        json={
            "category_id": expense_category["id"],
            "amount": "1200000.00",
            "currency": "COP",
            "description": "Rent March",
            "occurred_at": datetime(2026, 3, 3, tzinfo=timezone.utc).isoformat(),
        },
    )
    client.post(
        "/transactions/",
        json={
            "category_id": income_category["id"],
            "amount": "2500000.00",
            "currency": "COP",
            "description": "Salary March",
            "occurred_at": datetime(2026, 3, 1, tzinfo=timezone.utc).isoformat(),
        },
    )

    resp = client.get("/balance/monthly")
    assert resp.status_code == 200

    data = resp.json()
    assert data["current"] == {
        "month_start": "2026-03-01",
        "currency": "COP",
        "income": "2500000.00",
        "expense": "1200000.00",
        "balance": "1300000.00",
        "skipped_transactions": 0,
    }
    assert data["series"] == [
        {
            "month_start": "2026-03-01",
            "currency": "COP",
            "income": "2500000.00",
            "expense": "1200000.00",
            "balance": "1300000.00",
            "skipped_transactions": 0,
        },
        {
            "month_start": "2026-01-01",
            "currency": "COP",
            "income": "2500000.00",
            "expense": "0.00",
            "balance": "2500000.00",
            "skipped_transactions": 0,
        },
    ]


def test_balance_returns_zeroes_for_month_without_transactions(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    create_configured_user(client)

    resp = client.get("/balance/monthly?year=2026&month=2")
    assert resp.status_code == 200

    data = resp.json()
    assert data["current"] == {
        "month_start": "2026-02-01",
        "currency": "COP",
        "income": "0.00",
        "expense": "0.00",
        "balance": "0.00",
        "skipped_transactions": 0,
    }
    assert data["series"] == []


def test_balance_uses_user_timezone_for_month_boundaries(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    created = client.post(
        "/users/",
        json={
            "name": "Test User",
            "email": "test@example.com",
            "base_currency": "COP",
            "timezone": "America/Bogota",
        },
    )
    assert created.status_code == 200

    income_category = client.post(
        "/categories/",
        json={"name": "Salary", "direction": "income", "parent_id": None},
    ).json()

    created_tx = client.post(
        "/transactions/",
        json={
            "category_id": income_category["id"],
            "amount": "300000.00",
            "currency": "COP",
            "description": "Late night salary",
            "occurred_at": datetime(2026, 3, 1, 2, 30, tzinfo=timezone.utc).isoformat(),
        },
    )
    assert created_tx.status_code == 200

    february = client.get("/balance/monthly?year=2026&month=2")
    assert february.status_code == 200
    assert february.json()["current"] == {
        "month_start": "2026-02-01",
        "currency": "COP",
        "income": "300000.00",
        "expense": "0.00",
        "balance": "300000.00",
        "skipped_transactions": 0,
    }

    march = client.get("/balance/monthly?year=2026&month=3")
    assert march.status_code == 200
    assert march.json()["current"] == {
        "month_start": "2026-03-01",
        "currency": "COP",
        "income": "0.00",
        "expense": "0.00",
        "balance": "0.00",
        "skipped_transactions": 0,
    }


def test_balance_can_filter_by_financial_account_and_ignores_non_aggregated_types(
    client,
    db_session,
):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    created_user = create_configured_user(client)
    assert created_user.status_code == 200
    user = created_user.json()

    income_category = client.post(
        "/categories/",
        json={"name": "Salary", "direction": "income", "parent_id": None},
    ).json()
    expense_category = client.post(
        "/categories/",
        json={"name": "Bills", "direction": "expense", "parent_id": None},
    ).json()

    default_account = client.get("/financial-accounts/").json()[0]
    extra_account = client.post(
        "/financial-accounts/",
        json={"name": "Wallet"},
    ).json()

    client.post(
        "/transactions/",
        json={
            "financial_account_id": default_account["id"],
            "category_id": income_category["id"],
            "amount": "100000.00",
            "currency": "COP",
            "description": "Main salary",
            "occurred_at": datetime(2026, 3, 1, tzinfo=timezone.utc).isoformat(),
        },
    )
    client.post(
        "/transactions/",
        json={
            "financial_account_id": default_account["id"],
            "category_id": expense_category["id"],
            "amount": "40000.00",
            "currency": "COP",
            "description": "Main bills",
            "occurred_at": datetime(2026, 3, 2, tzinfo=timezone.utc).isoformat(),
        },
    )
    client.post(
        "/transactions/",
        json={
            "financial_account_id": extra_account["id"],
            "category_id": income_category["id"],
            "amount": "70000.00",
            "currency": "COP",
            "description": "Wallet salary",
            "occurred_at": datetime(2026, 3, 3, tzinfo=timezone.utc).isoformat(),
        },
    )
    client.post(
        "/transactions/",
        json={
            "financial_account_id": extra_account["id"],
            "category_id": expense_category["id"],
            "amount": "20000.00",
            "currency": "COP",
            "description": "Wallet bills",
            "occurred_at": datetime(2026, 3, 4, tzinfo=timezone.utc).isoformat(),
        },
    )

    db_session.add_all(
        [
            Transaction(
                user_id=UUID(user["id"]),
                financial_account_id=UUID(extra_account["id"]),
                category_id=None,
                transaction_type=TransactionType.transfer,
                amount="999999.00",
                currency="COP",
                base_currency="COP",
                amount_in_base_currency="999999.00",
                description="Internal transfer",
                occurred_at=datetime(2026, 3, 5, tzinfo=timezone.utc),
                created_at=datetime(2026, 3, 5, tzinfo=timezone.utc),
            ),
            Transaction(
                user_id=UUID(user["id"]),
                financial_account_id=UUID(extra_account["id"]),
                category_id=None,
                transaction_type=TransactionType.adjustment,
                amount="888888.00",
                currency="COP",
                base_currency="COP",
                amount_in_base_currency="888888.00",
                description="Legacy adjustment",
                occurred_at=datetime(2026, 3, 6, tzinfo=timezone.utc),
                created_at=datetime(2026, 3, 6, tzinfo=timezone.utc),
            ),
        ]
    )
    db_session.commit()

    consolidated = client.get("/balance/monthly?year=2026&month=3")
    assert consolidated.status_code == 200
    assert consolidated.json()["current"] == {
        "month_start": "2026-03-01",
        "currency": "COP",
        "income": "170000.00",
        "expense": "60000.00",
        "balance": "110000.00",
        "skipped_transactions": 0,
    }

    filtered = client.get(
        f"/balance/monthly?year=2026&month=3&financial_account_id={extra_account['id']}"
    )
    assert filtered.status_code == 200
    assert filtered.json()["current"] == {
        "month_start": "2026-03-01",
        "currency": "COP",
        "income": "70000.00",
        "expense": "20000.00",
        "balance": "50000.00",
        "skipped_transactions": 0,
    }
