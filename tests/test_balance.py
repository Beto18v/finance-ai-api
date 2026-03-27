from datetime import datetime, timezone


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
