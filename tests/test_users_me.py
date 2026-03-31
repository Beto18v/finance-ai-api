from datetime import datetime, timezone


def create_configured_user(client, **overrides):
    payload = {
        "name": "Test User",
        "email": "test@example.com",
        "base_currency": "COP",
        "timezone": "UTC",
    }
    payload.update(overrides)
    return client.post("/users/", json=payload)


def test_bootstrap_creates_profile_from_claims(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    created = client.post("/users/me/bootstrap")
    assert created.status_code == 200
    data = created.json()
    assert data["name"] == "Test User"
    assert data["email"] == "test@example.com"

    me = client.get("/users/me")
    assert me.status_code == 200
    assert me.json()["id"] == data["id"]


def test_bootstrap_prefers_explicit_name_and_updates_existing_profile(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    created = client.post(
        "/users/",
        json={"name": "Original Name", "email": "test@example.com"},
    )
    assert created.status_code == 200

    bootstrapped = client.post("/users/me/bootstrap", json={"name": "Google Name"})
    assert bootstrapped.status_code == 200
    assert bootstrapped.json()["name"] == "Google Name"
    assert bootstrapped.json()["email"] == "test@example.com"


def test_bootstrap_reactivates_profile_after_soft_deleted_account(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    created = client.post(
        "/users/",
        json={"name": "To Delete", "email": "test@example.com"},
    )
    assert created.status_code == 200

    deleted = client.delete("/users/me")
    assert deleted.status_code == 204

    bootstrapped = client.post("/users/me/bootstrap")
    assert bootstrapped.status_code == 200
    assert bootstrapped.json()["id"] == created.json()["id"]
    assert bootstrapped.json()["deleted_at"] is None
    assert bootstrapped.json()["email"] == "test@example.com"


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


def test_users_me_update_soft_delete_and_bootstrap_reactivation(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    created = create_configured_user(client)
    assert created.status_code == 200

    updated = client.put("/users/me", json={"name": "Updated User"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated User"

    deleted = client.delete("/users/me")
    assert deleted.status_code == 204

    missing = client.get("/users/me")
    assert missing.status_code == 404

    reactivated = client.post("/users/me/bootstrap", json={"name": "Reactivated User"})
    assert reactivated.status_code == 200
    assert reactivated.json()["id"] == created.json()["id"]
    assert reactivated.json()["deleted_at"] is None
    assert reactivated.json()["name"] == "Reactivated User"


def test_create_user_reactivates_soft_deleted_profile(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    created = create_configured_user(client)
    assert created.status_code == 200

    deleted = client.delete("/users/me")
    assert deleted.status_code == 204

    recreated = create_configured_user(client, name="Recreated User")
    assert recreated.status_code == 200
    assert recreated.json()["id"] == created.json()["id"]
    assert recreated.json()["deleted_at"] is None
    assert recreated.json()["name"] == "Recreated User"


def test_delete_account_preserves_categories_and_transactions_for_reactivation(client):
    cleanup = client.delete("/users/me")
    assert cleanup.status_code in (204, 404)

    created = create_configured_user(client)
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

    categories_while_deleted = client.get("/categories/")
    assert categories_while_deleted.status_code == 404

    reactivated = client.post("/users/me/bootstrap", json={"name": "Again"})
    assert reactivated.status_code == 200

    categories = client.get("/categories/")
    assert categories.status_code == 200
    categories_payload = categories.json()
    assert len(categories_payload) == 1
    assert categories_payload[0]["id"] == category_id
    assert categories_payload[0]["name"] == "Food"
    assert categories_payload[0]["direction"] == "expense"
    assert categories_payload[0]["parent_id"] is None

    transactions = client.get("/transactions/")
    assert transactions.status_code == 200
    assert transactions.json()["total_count"] == 1
    assert len(transactions.json()["items"]) == 1
    assert transactions.json()["summary"] == {
        "active_categories_count": 1,
        "skipped_transactions": 0,
        "income_totals": [],
        "expense_totals": [{"currency": "COP", "amount": "19.99"}],
        "balance_totals": [{"currency": "COP", "amount": "-19.99"}],
    }
