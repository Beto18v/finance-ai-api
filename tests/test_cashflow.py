from datetime import date


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


def create_obligation(
    client,
    *,
    name: str,
    amount: str,
    cadence: str,
    next_due_date: str,
    category_id: str,
    expected_financial_account_id: str | None = None,
    status: str | None = None,
):
    payload = {
        "name": name,
        "amount": amount,
        "cadence": cadence,
        "next_due_date": next_due_date,
        "category_id": category_id,
    }
    if expected_financial_account_id is not None:
        payload["expected_financial_account_id"] = expected_financial_account_id
    if status is not None:
        payload["status"] = status

    response = client.post("/obligations/", json=payload)
    assert response.status_code == 200
    return response.json()


def test_cashflow_forecast_projects_30_60_90_days_from_current_balance_and_confirmed_obligations(
    client,
    monkeypatch,
):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    create_configured_user(client, timezone_name="America/Bogota")
    default_account = client.get("/financial-accounts/").json()[0]
    fixed_costs = create_category(client, name="Fixed costs", direction="expense")

    opening_balance = client.post(
        "/adjustments/",
        json={
            "financial_account_id": default_account["id"],
            "balance_direction": "in",
            "amount": "1500.00",
            "currency": "COP",
            "description": "Opening balance",
            "occurred_at": "2026-04-01T12:00:00Z",
        },
    )
    assert opening_balance.status_code == 200

    create_obligation(
        client,
        name="Rent",
        amount="500.00",
        cadence="monthly",
        next_due_date="2026-04-15",
        category_id=fixed_costs["id"],
        expected_financial_account_id=default_account["id"],
    )
    create_obligation(
        client,
        name="Gym",
        amount="100.00",
        cadence="biweekly",
        next_due_date="2026-04-10",
        category_id=fixed_costs["id"],
    )
    create_obligation(
        client,
        name="Internet",
        amount="50.00",
        cadence="weekly",
        next_due_date="2026-04-12",
        category_id=fixed_costs["id"],
    )
    create_obligation(
        client,
        name="Insurance",
        amount="300.00",
        cadence="monthly",
        next_due_date="2026-06-01",
        category_id=fixed_costs["id"],
    )
    create_obligation(
        client,
        name="Paused",
        amount="999.00",
        cadence="monthly",
        next_due_date="2026-04-09",
        category_id=fixed_costs["id"],
        status="paused",
    )

    monkeypatch.setattr(
        "app.services.cashflow_service.resolve_obligation_reference_date",
        lambda _: date(2026, 4, 7),
    )

    response = client.get("/cashflow/forecast")
    assert response.status_code == 200

    data = response.json()
    assert data["reference_date"] == "2026-04-07"
    assert data["currency"] == "COP"
    assert data["current_balance"] == "1500.00"
    assert data["safe_to_spend"] == {
        "reference_date": "2026-04-07",
        "horizon_days": 30,
        "window_end_date": "2026-05-07",
        "currency": "COP",
        "current_balance": "1500.00",
        "scheduled_payments_count": 7,
        "confirmed_obligations_total": "900.00",
        "projected_balance": "600.00",
        "safe_to_spend": "600.00",
        "safe_to_spend_per_day": "20.00",
        "shortfall_amount": "0.00",
        "status": "covered",
    }
    assert data["horizons"] == [
        {
            "horizon_days": 30,
            "window_end_date": "2026-05-07",
            "scheduled_payments_count": 7,
            "confirmed_obligations_total": "900.00",
            "projected_balance": "600.00",
            "safe_to_spend": "600.00",
            "safe_to_spend_per_day": "20.00",
            "shortfall_amount": "0.00",
            "status": "covered",
        },
        {
            "horizon_days": 60,
            "window_end_date": "2026-06-06",
            "scheduled_payments_count": 16,
            "confirmed_obligations_total": "2200.00",
            "projected_balance": "-700.00",
            "safe_to_spend": "0.00",
            "safe_to_spend_per_day": "0.00",
            "shortfall_amount": "700.00",
            "status": "shortfall",
        },
        {
            "horizon_days": 90,
            "window_end_date": "2026-07-06",
            "scheduled_payments_count": 25,
            "confirmed_obligations_total": "3450.00",
            "projected_balance": "-1950.00",
            "safe_to_spend": "0.00",
            "safe_to_spend_per_day": "0.00",
            "shortfall_amount": "1950.00",
            "status": "shortfall",
        },
    ]


def test_safe_to_spend_counts_overdue_and_future_recurrences_inside_horizon(
    client,
    monkeypatch,
):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    create_configured_user(client, timezone_name="America/Bogota")
    default_account = client.get("/financial-accounts/").json()[0]
    fixed_costs = create_category(client, name="Fixed costs", direction="expense")

    opening_balance = client.post(
        "/adjustments/",
        json={
            "financial_account_id": default_account["id"],
            "balance_direction": "in",
            "amount": "300.00",
            "currency": "COP",
            "description": "Opening balance",
            "occurred_at": "2026-04-01T12:00:00Z",
        },
    )
    assert opening_balance.status_code == 200

    create_obligation(
        client,
        name="Rent",
        amount="200.00",
        cadence="monthly",
        next_due_date="2026-03-05",
        category_id=fixed_costs["id"],
        expected_financial_account_id=default_account["id"],
    )

    monkeypatch.setattr(
        "app.services.cashflow_service.resolve_obligation_reference_date",
        lambda _: date(2026, 4, 7),
    )

    response = client.get("/cashflow/safe-to-spend?horizon_days=45")
    assert response.status_code == 200
    assert response.json() == {
        "reference_date": "2026-04-07",
        "horizon_days": 45,
        "window_end_date": "2026-05-22",
        "currency": "COP",
        "current_balance": "300.00",
        "scheduled_payments_count": 3,
        "confirmed_obligations_total": "600.00",
        "projected_balance": "-300.00",
        "safe_to_spend": "0.00",
        "safe_to_spend_per_day": "0.00",
        "shortfall_amount": "300.00",
        "status": "shortfall",
    }
