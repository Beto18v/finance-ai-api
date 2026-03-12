from datetime import datetime, timezone


def test_balance_defaults_to_latest_month_with_data(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    client.post("/users/", json={"name": "Test User", "email": "test@example.com"})

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
        "income": "2500000.00",
        "expense": "1200000.00",
        "balance": "1300000.00",
    }
    assert data["series"] == [
        {
            "month_start": "2026-03-01",
            "income": "2500000.00",
            "expense": "1200000.00",
            "balance": "1300000.00",
        },
        {
            "month_start": "2026-01-01",
            "income": "2500000.00",
            "expense": "0.00",
            "balance": "2500000.00",
        },
    ]


def test_balance_returns_zeroes_for_month_without_transactions(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    client.post("/users/", json={"name": "Test User", "email": "test@example.com"})

    resp = client.get("/balance/monthly?year=2026&month=2")
    assert resp.status_code == 200

    data = resp.json()
    assert data["current"] == {
        "month_start": "2026-02-01",
        "income": "0.00",
        "expense": "0.00",
        "balance": "0.00",
    }
    assert data["series"] == []