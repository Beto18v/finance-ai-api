import uuid
from datetime import datetime, timezone


def test_create_category(client):
    # Ensure profile exists
    client.post("/users/", json={"name": "Test User", "email": "test@example.com"})

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
    client.post("/users/", json={"name": "Test User", "email": "test@example.com"})

    resp = client.post(
        "/transactions/",
        json={
            "category_id": str(uuid.uuid4()),
            "amount": "10.50",
            "currency": "COP",
            "description": "Coffee",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert resp.status_code == 404


def test_create_and_list_transactions(client):
    client.post("/users/", json={"name": "Test User", "email": "test@example.com"})

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
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert tx.status_code == 200

    listed = client.get("/transactions/")
    assert listed.status_code == 200
    assert isinstance(listed.json(), list)
    assert len(listed.json()) >= 1


def test_category_crud(client):
    client.post("/users/", json={"name": "Test User", "email": "test@example.com"})

    created = client.post(
        "/categories/",
        json={"name": "Groceries", "direction": "expense", "parent_id": None},
    )
    assert created.status_code == 200
    category_id = created.json()["id"]

    fetched = client.get(f"/categories/{category_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Groceries"

    updated = client.put(
        f"/categories/{category_id}",
        json={"name": "Supermarket"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Supermarket"

    deleted = client.delete(f"/categories/{category_id}")
    assert deleted.status_code == 204

    missing = client.get(f"/categories/{category_id}")
    assert missing.status_code == 404


def test_create_duplicate_category_returns_conflict(client):
    client.post("/users/", json={"name": "Test User", "email": "test@example.com"})

    created = client.post(
        "/categories/",
        json={"name": "Groceries", "direction": "expense", "parent_id": None},
    )
    assert created.status_code == 200

    duplicated = client.post(
        "/categories/",
        json={"name": " groceries ", "direction": "income", "parent_id": None},
    )
    assert duplicated.status_code == 409
    assert duplicated.json()["detail"] == "Category already exists"


def test_update_category_to_duplicate_name_returns_conflict(client):
    client.post("/users/", json={"name": "Test User", "email": "test@example.com"})

    first_category = client.post(
        "/categories/",
        json={"name": "Groceries", "direction": "expense", "parent_id": None},
    )
    assert first_category.status_code == 200

    second_category = client.post(
        "/categories/",
        json={"name": "Transport", "direction": "expense", "parent_id": None},
    )
    assert second_category.status_code == 200

    updated = client.put(
        f"/categories/{second_category.json()['id']}",
        json={"name": " groceries "},
    )
    assert updated.status_code == 409
    assert updated.json()["detail"] == "Category already exists"


def test_transaction_crud(client):
    client.post("/users/", json={"name": "Test User", "email": "test@example.com"})

    cat = client.post(
        "/categories/",
        json={"name": "Transport", "direction": "expense", "parent_id": None},
    ).json()

    created = client.post(
        "/transactions/",
        json={
            "category_id": cat["id"],
            "amount": "15.25",
            "currency": "COP",
            "description": "Taxi",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert created.status_code == 200
    transaction_id = created.json()["id"]

    fetched = client.get(f"/transactions/{transaction_id}")
    assert fetched.status_code == 200
    assert fetched.json()["description"] == "Taxi"

    updated = client.put(
        f"/transactions/{transaction_id}",
        json={"description": "Cab"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Cab"

    deleted = client.delete(f"/transactions/{transaction_id}")
    assert deleted.status_code == 204

    missing = client.get(f"/transactions/{transaction_id}")
    assert missing.status_code == 404
