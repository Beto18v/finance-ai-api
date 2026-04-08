from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from app.models.obligation import Obligation
from app.models.transaction import Transaction, TransactionType
from app.schemas.obligation import ObligationMarkPaid
from app.services.obligation_service import mark_obligation_paid


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
    source_recurring_candidate_key: str | None = None,
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
    if source_recurring_candidate_key is not None:
        payload["source_recurring_candidate_key"] = source_recurring_candidate_key
    if status is not None:
        payload["status"] = status

    response = client.post("/obligations/", json=payload)
    assert response.status_code == 200
    return response.json()


def test_create_obligation_and_manage_statuses(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    create_configured_user(client)
    default_account = client.get("/financial-accounts/").json()[0]
    rent = create_category(client, name="Rent", direction="expense")
    salary = create_category(client, name="Salary", direction="income")

    created = create_obligation(
        client,
        name="Arriendo",
        amount="1200000.00",
        cadence="monthly",
        next_due_date="2026-04-15",
        category_id=rent["id"],
        expected_financial_account_id=default_account["id"],
        source_recurring_candidate_key="candidate-rent-001",
    )
    assert created["name"] == "Arriendo"
    assert created["status"] == "active"
    assert created["cadence"] == "monthly"
    assert created["currency"] == "COP"
    assert created["category_id"] == rent["id"]
    assert created["category_name"] == "Rent"
    assert created["expected_financial_account_id"] == default_account["id"]
    assert created["expected_financial_account_name"] == "Main account"
    assert created["source_recurring_candidate_key"] == "candidate-rent-001"

    invalid = client.post(
        "/obligations/",
        json={
            "name": "Nomina esperada",
            "amount": "2500000.00",
            "cadence": "monthly",
            "next_due_date": "2026-04-30",
            "category_id": salary["id"],
        },
    )
    assert invalid.status_code == 409
    assert invalid.json()["detail"] == "Only expense categories can be used for obligations"

    paused = client.patch(
        f"/obligations/{created['id']}",
        json={"status": "paused"},
    )
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    archived = client.patch(
        f"/obligations/{created['id']}",
        json={"status": "archived"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    second = create_obligation(
        client,
        name="Internet",
        amount="99000.00",
        cadence="monthly",
        next_due_date="2026-04-22",
        category_id=rent["id"],
    )
    listed = client.get("/obligations/")
    assert listed.status_code == 200
    assert listed.json()["counts"] == {
        "active": 1,
        "paused": 0,
        "archived": 1,
    }
    assert [item["id"] for item in listed.json()["items"]] == [
        second["id"],
        created["id"],
    ]


def test_upcoming_obligations_calculate_urgency_and_expected_account_risk(
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
            "amount": "200.00",
            "currency": "COP",
            "description": "Opening balance",
            "occurred_at": "2026-04-01T12:00:00Z",
        },
    )
    assert opening_balance.status_code == 200

    overdue = create_obligation(
        client,
        name="Water",
        amount="80.00",
        cadence="monthly",
        next_due_date="2026-04-05",
        category_id=fixed_costs["id"],
    )
    due_today = create_obligation(
        client,
        name="Rent",
        amount="500.00",
        cadence="monthly",
        next_due_date="2026-04-07",
        category_id=fixed_costs["id"],
        expected_financial_account_id=default_account["id"],
    )
    due_soon = create_obligation(
        client,
        name="Internet",
        amount="120.00",
        cadence="monthly",
        next_due_date="2026-04-12",
        category_id=fixed_costs["id"],
    )
    upcoming = create_obligation(
        client,
        name="Insurance",
        amount="300.00",
        cadence="monthly",
        next_due_date="2026-04-25",
        category_id=fixed_costs["id"],
    )
    create_obligation(
        client,
        name="Paused",
        amount="50.00",
        cadence="monthly",
        next_due_date="2026-04-09",
        category_id=fixed_costs["id"],
        status="paused",
    )

    monkeypatch.setattr(
        "app.services.obligation_service.resolve_obligation_reference_date",
        lambda _: date(2026, 4, 7),
    )

    response = client.get("/obligations/upcoming?days_ahead=30&limit=10")
    assert response.status_code == 200

    data = response.json()
    assert data["reference_date"] == "2026-04-07"
    assert data["window_end_date"] == "2026-05-07"
    assert data["summary"] == {
        "currency": "COP",
        "total_active": 4,
        "items_in_window": 4,
        "overdue_count": 1,
        "due_today_count": 1,
        "due_soon_count": 1,
        "expected_account_risk_count": 1,
        "total_expected_amount": "1000.00",
    }
    assert [item["id"] for item in data["items"]] == [
        overdue["id"],
        due_today["id"],
        due_soon["id"],
        upcoming["id"],
    ]

    assert data["items"][0]["urgency"] == "overdue"
    assert data["items"][0]["days_until_due"] == -2

    assert data["items"][1]["urgency"] == "today"
    assert data["items"][1]["expected_account_current_balance"] == "200.00"
    assert data["items"][1]["expected_account_shortfall_amount"] == "300.00"

    assert data["items"][2]["urgency"] == "soon"
    assert data["items"][2]["days_until_due"] == 5

    assert data["items"][3]["urgency"] == "upcoming"
    assert data["items"][3]["days_until_due"] == 18

    limited_response = client.get("/obligations/upcoming?days_ahead=30&limit=2")
    assert limited_response.status_code == 200

    limited_data = limited_response.json()
    assert limited_data["summary"] == {
        "currency": "COP",
        "total_active": 4,
        "items_in_window": 4,
        "overdue_count": 1,
        "due_today_count": 1,
        "due_soon_count": 1,
        "expected_account_risk_count": 1,
        "total_expected_amount": "1000.00",
    }
    assert [item["id"] for item in limited_data["items"]] == [
        overdue["id"],
        due_today["id"],
    ]


def test_mark_paid_creates_real_expense_and_advances_month_end_due_date(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    create_configured_user(client)
    default_account = client.get("/financial-accounts/").json()[0]
    rent = create_category(client, name="Rent", direction="expense")
    obligation = create_obligation(
        client,
        name="Monthly rent",
        amount="1200000.00",
        cadence="monthly",
        next_due_date="2026-01-31",
        category_id=rent["id"],
        expected_financial_account_id=default_account["id"],
    )

    first_payment = client.post(
        f"/obligations/{obligation['id']}/mark-paid",
        json={
            "paid_at": "2026-01-31T15:00:00Z",
        },
    )
    assert first_payment.status_code == 200
    first_data = first_payment.json()
    assert first_data["obligation"]["next_due_date"] == "2026-02-28"
    assert first_data["transaction"]["transaction_type"] == "expense"
    assert first_data["transaction"]["category_id"] == rent["id"]
    assert first_data["transaction"]["financial_account_id"] == default_account["id"]
    assert first_data["transaction"]["description"] == "Monthly rent"
    assert first_data["transaction"]["amount"] == "1200000.00"

    second_payment = client.post(
        f"/obligations/{obligation['id']}/mark-paid",
        json={
            "paid_at": "2026-02-28T15:00:00Z",
        },
    )
    assert second_payment.status_code == 200
    assert second_payment.json()["obligation"]["next_due_date"] == "2026-03-31"

    transactions = client.get("/transactions/")
    assert transactions.status_code == 200
    assert transactions.json()["total_count"] == 2
    assert [item["description"] for item in transactions.json()["items"]] == [
        "Monthly rent",
        "Monthly rent",
    ]
    assert all(
        item["transaction_type"] == "expense"
        for item in transactions.json()["items"]
    )


def test_delete_obligation_does_not_remove_paid_expenses(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    create_configured_user(client)
    default_account = client.get("/financial-accounts/").json()[0]
    rent = create_category(client, name="Rent", direction="expense")
    obligation = create_obligation(
        client,
        name="Monthly rent",
        amount="1200000.00",
        cadence="monthly",
        next_due_date="2026-01-31",
        category_id=rent["id"],
        expected_financial_account_id=default_account["id"],
    )

    payment = client.post(
        f"/obligations/{obligation['id']}/mark-paid",
        json={
            "paid_at": "2026-01-31T15:00:00Z",
        },
    )
    assert payment.status_code == 200

    deleted = client.delete(f"/obligations/{obligation['id']}")
    assert deleted.status_code == 204

    listed = client.get("/obligations/")
    assert listed.status_code == 200
    assert listed.json()["counts"] == {
        "active": 0,
        "paused": 0,
        "archived": 0,
    }
    assert listed.json()["items"] == []

    transactions = client.get("/transactions/")
    assert transactions.status_code == 200
    assert transactions.json()["total_count"] == 1
    assert transactions.json()["items"][0]["description"] == "Monthly rent"
    assert transactions.json()["items"][0]["category_id"] == rent["id"]


def test_mark_paid_rolls_back_when_commit_fails(client, db_session, monkeypatch):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    user = create_configured_user(client)
    default_account = client.get("/financial-accounts/").json()[0]
    utilities = create_category(client, name="Utilities", direction="expense")
    obligation_data = create_obligation(
        client,
        name="Power bill",
        amount="150000.00",
        cadence="monthly",
        next_due_date="2026-04-20",
        category_id=utilities["id"],
        expected_financial_account_id=default_account["id"],
    )
    obligation_id = UUID(obligation_data["id"])

    def failing_commit():
        raise RuntimeError("forced commit failure")

    monkeypatch.setattr(db_session, "commit", failing_commit)

    with pytest.raises(RuntimeError, match="forced commit failure"):
        mark_obligation_paid(
            db_session,
            UUID(user["id"]),
            obligation_id,
            ObligationMarkPaid(
                financial_account_id=UUID(default_account["id"]),
                paid_at=datetime(2026, 4, 20, 14, tzinfo=timezone.utc),
            ),
        )

    db_session.expire_all()
    stored_obligation = (
        db_session.query(Obligation)
        .filter(Obligation.id == obligation_id)
        .first()
    )
    assert stored_obligation is not None
    assert stored_obligation.next_due_date == date(2026, 4, 20)

    transaction_count = int(
        db_session.query(Transaction.id)
        .filter(
            Transaction.user_id == UUID(user["id"]),
            Transaction.transaction_type == TransactionType.expense,
            Transaction.description == "Power bill",
        )
        .count()
    )
    assert transaction_count == 0
