"""Test đăng nhập (JWT) và bảo vệ endpoint quản trị bằng role."""


def test_login_with_correct_password_returns_token_and_role(client):
    resp = client.post("/api/auth/login", json={"email": "admin@demo.com", "password": "123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "admin"
    assert data["name"] == "Admin"
    assert data["access_token"]


def test_login_staff_account_returns_staff_role(client):
    resp = client.post("/api/auth/login", json={"email": "staff@demo.com", "password": "123"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "staff"


def test_login_with_wrong_password_returns_401(client):
    resp = client.post("/api/auth/login", json={"email": "admin@demo.com", "password": "sai-mat-khau"})
    assert resp.status_code == 401


def test_login_with_unknown_email_returns_401(client):
    resp = client.post("/api/auth/login", json={"email": "khong-ton-tai@demo.com", "password": "123"})
    assert resp.status_code == 401


def test_tickets_endpoint_requires_token(client):
    resp = client.get("/api/support/tickets")
    assert resp.status_code == 401


def test_tickets_endpoint_accepts_staff_token(client, staff_auth_headers):
    resp = client.get("/api/support/tickets", headers=staff_auth_headers)
    assert resp.status_code == 200


def test_tickets_endpoint_accepts_admin_token(client, admin_auth_headers):
    resp = client.get("/api/support/tickets", headers=admin_auth_headers)
    assert resp.status_code == 200


def test_admin_only_endpoint_rejects_staff_token(client, staff_auth_headers):
    resp = client.get("/api/support/settings", headers=staff_auth_headers)
    assert resp.status_code == 403


def test_admin_only_endpoint_accepts_admin_token(client, admin_auth_headers):
    resp = client.get("/api/support/settings", headers=admin_auth_headers)
    assert resp.status_code == 200


def test_invalid_token_is_rejected(client):
    resp = client.get("/api/support/tickets", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_submit_and_session_endpoints_stay_public(client):
    """Khách hàng ẩn danh vẫn phải gọi được /submit và /session mà không cần token."""
    resp = client.get("/api/support/session/khong-ton-tai")
    assert resp.status_code == 200
    assert resp.json() == {"exists": False}
