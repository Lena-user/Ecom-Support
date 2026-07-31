"""Test quản lý tài khoản nhân viên/admin (staff_store, cần role admin)."""

from app.auth import create_access_token
from app.graph import nodes as nodes_module

SUBMIT_URL = "/api/support/submit"


def test_list_staff_requires_admin(client, staff_auth_headers):
    resp = client.get("/api/support/staff", headers=staff_auth_headers)
    assert resp.status_code == 403


def test_list_staff_requires_token(client):
    resp = client.get("/api/support/staff")
    assert resp.status_code == 401


def test_list_staff_returns_seeded_demo_accounts(client, admin_auth_headers):
    resp = client.get("/api/support/staff", headers=admin_auth_headers)
    assert resp.status_code == 200
    emails = {s["email"] for s in resp.json()}
    assert emails == {"admin@demo.com", "staff@demo.com", "staff2@demo.com"}
    # không được lộ password_hash
    assert all("password_hash" not in s for s in resp.json())


def test_create_staff_then_login_with_new_account(client, admin_auth_headers):
    create_resp = client.post(
        "/api/support/staff",
        json={"email": "new_staff@demo.com", "name": "Nguyễn Văn C", "password": "matkhaumoi", "role": "staff"},
        headers=admin_auth_headers,
    )
    assert create_resp.status_code == 200

    login_resp = client.post(
        "/api/auth/login", json={"email": "new_staff@demo.com", "password": "matkhaumoi"}
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["role"] == "staff"


def test_create_staff_duplicate_email_returns_409(client, admin_auth_headers):
    resp = client.post(
        "/api/support/staff",
        json={"email": "staff@demo.com", "name": "Trùng email", "password": "abcdef", "role": "staff"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 409


def test_cannot_delete_self(client, admin_auth_headers):
    resp = client.delete("/api/support/staff/admin@demo.com", headers=admin_auth_headers)
    assert resp.status_code == 400


def test_cannot_delete_last_admin(client):
    """Dùng token của 1 admin khác (không qua store, chỉ ký JWT trực tiếp) để
    thử xoá admin@demo.com — vốn là admin duy nhất trong store lúc này."""
    other_admin_token = create_access_token(email="someone-else@demo.com", role="admin", name="Khác")
    resp = client.delete(
        "/api/support/staff/admin@demo.com",
        headers={"Authorization": f"Bearer {other_admin_token}"},
    )
    assert resp.status_code == 400


def test_delete_staff_succeeds_for_non_admin_target(client, admin_auth_headers):
    resp = client.delete("/api/support/staff/staff2@demo.com", headers=admin_auth_headers)
    assert resp.status_code == 200

    list_resp = client.get("/api/support/staff", headers=admin_auth_headers)
    emails = {s["email"] for s in list_resp.json()}
    assert "staff2@demo.com" not in emails


def test_ticket_count_survives_closing_the_ticket(client, monkeypatch, admin_auth_headers, staff_auth_headers):
    """Bug thực tế: close_ticket() từng xoá staff_assigned về None khi đóng ca,
    khiến "Tickets xử lý" ở Quản lý nhân sự luôn ra 0 cho mọi ticket đã đóng
    (và tab "Đã xong" ở Dashboard, lọc theo staff_assigned, cũng luôn rỗng)."""
    monkeypatch.setattr(
        nodes_module,
        "classify_message",
        lambda message, channel: {
            "classification": "complaint",
            "priority": "high",
            "has_sufficient_info": True,
            "requires_human": True,
            "reasoning": "test",
        },
    )

    customer_id = "cust_ticket_count"
    client.post(SUBMIT_URL, json={"customer_id": customer_id, "channel": "web_chat", "message": "Hàng bị lỗi"})

    client.post(f"/api/support/tickets/{customer_id}/accept", json={"staff_name": "Linh Nguyễn"}, headers=staff_auth_headers)
    close_resp = client.post(f"/api/support/tickets/{customer_id}/close", headers=staff_auth_headers)
    assert close_resp.json()["success"] is True

    staff_resp = client.get("/api/support/staff", headers=admin_auth_headers)
    linh = next(s for s in staff_resp.json() if s["email"] == "staff@demo.com")
    assert linh["ticket_count"] >= 1

    tickets_resp = client.get("/api/support/tickets", headers=staff_auth_headers)
    ticket = next(t for t in tickets_resp.json() if t["id"] == customer_id)
    assert ticket["status"] == "RESOLVED"
    assert ticket["staff_assigned"] == "Linh Nguyễn"  # không bị xoá sau khi đóng ca


def test_ticket_count_accumulates_across_multiple_escalation_rounds(client, monkeypatch, admin_auth_headers, staff_auth_headers):
    """Giới hạn thiết kế đã fix: staff_assigned chỉ giữ được 1 tên tại 1 thời
    điểm, bị ghi đè mỗi vòng escalate mới — nếu chỉ đếm theo field đó thì công
    của vòng trước (do nhân viên khác xử lý) sẽ mất khỏi "Tickets xử lý" ngay
    khi vòng escalate tiếp theo bắt đầu. Giờ đếm theo lịch sử "handled_by" nên
    cả 2 nhân viên của 2 vòng khác nhau đều phải được ghi nhận."""
    monkeypatch.setattr(
        nodes_module,
        "classify_message",
        lambda message, channel: {
            "classification": "complaint",
            "priority": "high",
            "has_sufficient_info": True,
            "requires_human": True,
            "reasoning": "test",
        },
    )
    admin2_headers = {"Authorization": f"Bearer {create_access_token(email='staff2@demo.com', role='staff', name='Minh Trần')}"}

    customer_id = "cust_multi_round"

    # Vòng 1 — Linh Nguyễn tiếp nhận rồi đóng ca
    client.post(SUBMIT_URL, json={"customer_id": customer_id, "channel": "web_chat", "message": "Hàng bị lỗi lần 1"})
    client.post(f"/api/support/tickets/{customer_id}/accept", json={"staff_name": "Linh Nguyễn"}, headers=staff_auth_headers)
    client.post(f"/api/support/tickets/{customer_id}/close", headers=staff_auth_headers)

    # Vòng 2 — cùng khách hàng đó escalate lại, lần này Minh Trần tiếp nhận
    client.post(SUBMIT_URL, json={"customer_id": customer_id, "channel": "web_chat", "message": "Hàng bị lỗi lần 2"})
    client.post(f"/api/support/tickets/{customer_id}/accept", json={"staff_name": "Minh Trần"}, headers=admin2_headers)
    client.post(f"/api/support/tickets/{customer_id}/close", headers=admin2_headers)

    staff_resp = client.get("/api/support/staff", headers=admin_auth_headers)
    accounts = {s["email"]: s for s in staff_resp.json()}
    assert accounts["staff@demo.com"]["ticket_count"] >= 1   # Linh — vòng 1
    assert accounts["staff2@demo.com"]["ticket_count"] >= 1  # Minh — vòng 2
