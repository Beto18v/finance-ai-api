def test_users_me_creates_profile(client):
    resp = client.get("/users/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["email"] == "test@example.com"
