from datetime import datetime, timezone


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
    occurred_at: datetime,
    description: str | None = None,
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


def test_recurring_candidates_detects_description_and_amount_fallback_patterns(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    create_configured_user(client)
    rent = create_category(client, name="Rent", direction="expense")
    salary = create_category(client, name="Salary", direction="income")
    app_income = create_category(client, name="Platform income", direction="income")

    create_transaction(
        client,
        category_id=rent["id"],
        amount="1200000.00",
        description="Apartment rent",
        occurred_at=datetime(2026, 1, 5, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        category_id=rent["id"],
        amount="1200000.00",
        description="Apartment rent",
        occurred_at=datetime(2026, 2, 5, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        category_id=rent["id"],
        amount="1210000.00",
        description="Apartment rent",
        occurred_at=datetime(2026, 3, 5, 12, tzinfo=timezone.utc),
    )

    create_transaction(
        client,
        category_id=salary["id"],
        amount="2500000.00",
        description=None,
        occurred_at=datetime(2026, 1, 30, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        category_id=salary["id"],
        amount="2500000.00",
        description=None,
        occurred_at=datetime(2026, 2, 28, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        category_id=salary["id"],
        amount="2500000.00",
        description=None,
        occurred_at=datetime(2026, 3, 30, 12, tzinfo=timezone.utc),
    )

    for occurred_at, amount in (
        (datetime(2026, 3, 1, 12, tzinfo=timezone.utc), "12000.00"),
        (datetime(2026, 3, 2, 12, tzinfo=timezone.utc), "25000.00"),
        (datetime(2026, 3, 5, 12, tzinfo=timezone.utc), "9000.00"),
        (datetime(2026, 3, 9, 12, tzinfo=timezone.utc), "31000.00"),
    ):
        create_transaction(
            client,
            category_id=app_income["id"],
            amount=amount,
            description="App payout",
            occurred_at=occurred_at,
        )

    response = client.get("/analytics/recurring-candidates?year=2026&month=3")
    assert response.status_code == 200

    data = response.json()
    assert data["month_start"] == "2026-03-01"
    assert data["history_window_start"] == "2025-03-01"
    assert len(data["candidates"]) == 2

    rent_candidate = next(
        item for item in data["candidates"] if item["category_name"] == "Rent"
    )
    assert rent_candidate == {
        "label": "Apartment rent",
        "description": "Apartment rent",
        "category_id": rent["id"],
        "category_name": "Rent",
        "direction": "expense",
        "cadence": "monthly",
        "match_basis": "description",
        "amount_pattern": "stable",
        "currency": "COP",
        "typical_amount": "1203333.33",
        "amount_min": "1200000.00",
        "amount_max": "1210000.00",
        "occurrence_count": 3,
        "interval_days": [31, 28],
        "first_occurred_at": "2026-01-05T12:00:00Z",
        "last_occurred_at": "2026-03-05T12:00:00Z",
    }

    salary_candidate = next(
        item for item in data["candidates"] if item["category_name"] == "Salary"
    )
    assert salary_candidate == {
        "label": "Salary",
        "description": None,
        "category_id": salary["id"],
        "category_name": "Salary",
        "direction": "income",
        "cadence": "monthly",
        "match_basis": "category_amount",
        "amount_pattern": "exact",
        "currency": "COP",
        "typical_amount": "2500000.00",
        "amount_min": "2500000.00",
        "amount_max": "2500000.00",
        "occurrence_count": 3,
        "interval_days": [29, 30],
        "first_occurred_at": "2026-01-30T12:00:00Z",
        "last_occurred_at": "2026-03-30T12:00:00Z",
    }


def test_recurring_candidates_require_recent_activity_in_selected_month(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    create_configured_user(client)
    streaming = create_category(client, name="Streaming", direction="expense")

    create_transaction(
        client,
        category_id=streaming["id"],
        amount="39900.00",
        description="Streaming subscription",
        occurred_at=datetime(2026, 1, 8, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        category_id=streaming["id"],
        amount="39900.00",
        description="Streaming subscription",
        occurred_at=datetime(2026, 2, 8, 12, tzinfo=timezone.utc),
    )
    create_transaction(
        client,
        category_id=streaming["id"],
        amount="39900.00",
        description="Streaming subscription",
        occurred_at=datetime(2026, 3, 8, 12, tzinfo=timezone.utc),
    )

    april = client.get("/analytics/recurring-candidates?year=2026&month=4")
    assert april.status_code == 200
    assert april.json() == {
        "month_start": "2026-04-01",
        "history_window_start": "2025-04-01",
        "candidates": [],
    }


def test_recurring_candidates_can_filter_by_financial_account(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    create_configured_user(client)
    salary = create_category(client, name="Salary", direction="income")
    default_account = client.get("/financial-accounts/").json()[0]
    wallet = client.post("/financial-accounts/", json={"name": "Wallet"}).json()

    for occurred_at in (
        datetime(2026, 1, 30, 12, tzinfo=timezone.utc),
        datetime(2026, 2, 28, 12, tzinfo=timezone.utc),
        datetime(2026, 3, 30, 12, tzinfo=timezone.utc),
    ):
        create_transaction(
            client,
            financial_account_id=default_account["id"],
            category_id=salary["id"],
            amount="2500000.00",
            description="Main payroll",
            occurred_at=occurred_at,
        )

    for occurred_at in (
        datetime(2026, 1, 15, 12, tzinfo=timezone.utc),
        datetime(2026, 2, 15, 12, tzinfo=timezone.utc),
        datetime(2026, 3, 15, 12, tzinfo=timezone.utc),
    ):
        create_transaction(
            client,
            financial_account_id=wallet["id"],
            category_id=salary["id"],
            amount="500000.00",
            description="Wallet stipend",
            occurred_at=occurred_at,
        )

    filtered = client.get(
        f"/analytics/recurring-candidates?year=2026&month=3&financial_account_id={wallet['id']}"
    )
    assert filtered.status_code == 200
    assert filtered.json() == {
        "month_start": "2026-03-01",
        "history_window_start": "2025-03-01",
        "candidates": [
            {
                "label": "Wallet stipend",
                "description": "Wallet stipend",
                "category_id": salary["id"],
                "category_name": "Salary",
                "direction": "income",
                "cadence": "monthly",
                "match_basis": "description",
                "amount_pattern": "exact",
                "currency": "COP",
                "typical_amount": "500000.00",
                "amount_min": "500000.00",
                "amount_max": "500000.00",
                "occurrence_count": 3,
                "interval_days": [31, 28],
                "first_occurred_at": "2026-01-15T12:00:00Z",
                "last_occurred_at": "2026-03-15T12:00:00Z",
            }
        ],
    }
