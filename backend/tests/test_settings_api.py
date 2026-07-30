"""Test GET/PUT /api/support/settings — cấu hình AI (Admin > Cấu hình AI, cần role admin)."""


def test_get_settings_returns_defaults(client, admin_auth_headers):
    resp = client.get("/api/support/settings", headers=admin_auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["similarity_threshold"] == 0.65
    assert data["duplicate_window_hours"] == 24
    assert isinstance(data["escalate_keywords"], list)


def test_put_settings_persists_and_matches_subsequent_get(client, admin_auth_headers):
    payload = {
        "similarity_threshold": 0.8,
        "duplicate_window_hours": 12,
        "escalate_keywords": ["kiện", "tòa án"],
    }
    put_resp = client.put("/api/support/settings", json=payload, headers=admin_auth_headers)
    assert put_resp.status_code == 200
    assert put_resp.json() == payload

    get_resp = client.get("/api/support/settings", headers=admin_auth_headers)
    assert get_resp.json() == payload


def test_put_settings_rejects_threshold_out_of_range(client, admin_auth_headers):
    resp = client.put(
        "/api/support/settings",
        json={"similarity_threshold": 1.5, "duplicate_window_hours": 24, "escalate_keywords": []},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 422


def test_settings_requires_auth(client):
    resp = client.get("/api/support/settings")
    assert resp.status_code == 401


def test_settings_requires_admin_role(client, staff_auth_headers):
    resp = client.get("/api/support/settings", headers=staff_auth_headers)
    assert resp.status_code == 403
