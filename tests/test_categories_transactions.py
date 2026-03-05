import uuid
from datetime import datetime, timezone


def test_create_category(client):
    # Ensure profile exists
    client.get("/users/me")

    resp = client.post(
        "/categories/",
        json={"name": "Salary", "direction": "income", "parent_id": None},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Salary"
    assert data["direction"] == "income"


def test_create_transaction_requires_existing_category(client):
    # Ensure profile exists
    client.get("/users/me")

    resp = client.post(
        "/transactions/",
        json={
            "category_id": str(uuid.uuid4()),
            "amount": "10.50",
            "currency": "COP",
            "description": "Coffee",
            "merchant_name": "Cafe",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert resp.status_code == 404


def test_create_and_list_transactions(client):
    client.get("/users/me")

    cat = client.post(
        "/categories/",
        json={"name": "Food", "direction": "expense", "parent_id": None},
    ).json()

    tx = client.post(
        "/transactions/",
        json={
            "category_id": cat["id"],
            "amount": "25.00",
            "currency": "COP",
            "description": "Lunch",
            "merchant_name": "Restaurant",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert tx.status_code == 200

    listed = client.get("/transactions/")
    assert listed.status_code == 200
    assert isinstance(listed.json(), list)
    assert len(listed.json()) >= 1
