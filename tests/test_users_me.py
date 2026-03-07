from datetime import datetime, timezone


def test_users_me_requires_existing_active_profile(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    missing = client.get("/users/me")
    assert missing.status_code == 404

    created = client.post(
        "/users/",
        json={"name": "Test User", "email": "test@example.com"},
    )
    assert created.status_code == 200

    resp = client.get("/users/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["email"] == "test@example.com"


def test_users_me_update_soft_delete_and_explicit_recreate(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    created = client.post(
        "/users/",
        json={"name": "Test User", "email": "test@example.com"},
    )
    assert created.status_code == 200

    updated = client.put("/users/me", json={"name": "Updated User"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated User"

    deleted = client.delete("/users/me")
    assert deleted.status_code == 204

    # Deleted users are not auto-restored by /users/me.
    missing = client.get("/users/me")
    assert missing.status_code == 404

    recreated = client.post(
        "/users/",
        json={"name": "Recreated User", "email": "test@example.com"},
    )
    assert recreated.status_code == 200
    assert recreated.json()["deleted_at"] is None
    assert recreated.json()["name"] == "Recreated User"


def test_delete_account_purges_categories_and_transactions(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    created = client.post(
        "/users/",
        json={"name": "Test User", "email": "test@example.com"},
    )
    assert created.status_code == 200

    category = client.post(
        "/categories/",
        json={"name": "Food", "direction": "expense", "parent_id": None},
    )
    assert category.status_code == 200
    category_id = category.json()["id"]

    tx = client.post(
        "/transactions/",
        json={
            "category_id": category_id,
            "amount": "19.99",
            "currency": "COP",
            "description": "Lunch",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert tx.status_code == 200

    deleted = client.delete("/users/me")
    assert deleted.status_code == 204

    missing = client.get("/users/me")
    assert missing.status_code == 404

    recreated = client.post(
        "/users/",
        json={"name": "Again", "email": "test@example.com"},
    )
    assert recreated.status_code == 200

    categories = client.get("/categories/")
    assert categories.status_code == 200
    assert categories.json() == []

    transactions = client.get("/transactions/")
    assert transactions.status_code == 200
    assert transactions.json() == []
