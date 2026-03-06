def test_users_me_creates_profile(client):
    resp = client.get("/users/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["email"] == "test@example.com"


def test_users_me_update_and_soft_delete_restore(client):
    resp = client.get("/users/me")
    assert resp.status_code == 200

    updated = client.put("/users/me", json={"name": "Updated User"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated User"

    deleted = client.delete("/users/me")
    assert deleted.status_code == 204

    # Returning to /users/me should reactivate the same profile row.
    restored = client.get("/users/me")
    assert restored.status_code == 200
    assert restored.json()["deleted_at"] is None
    assert restored.json()["name"] == "Updated User"
