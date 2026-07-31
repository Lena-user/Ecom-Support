"""Test tính năng đính kèm ảnh (POST /upload + attachment_url trong /submit)."""

import asyncio

from app import session_store as session_store_module
from app.graph import nodes as nodes_module

UPLOAD_URL = "/api/support/upload"
SUBMIT_URL = "/api/support/submit"

# PNG 1x1 pixel hợp lệ (bytes nhỏ nhất có thể) — đủ để pass content-type check
_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100e221bc330000000049454e44ae426082"
)


def _mock_escalated(monkeypatch):
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


def test_upload_valid_image_returns_url(client):
    resp = client.post(UPLOAD_URL, files={"file": ("photo.png", _TINY_PNG, "image/png")})
    assert resp.status_code == 200
    assert resp.json()["url"].startswith("/uploads/")


def test_upload_rejects_disallowed_type(client):
    resp = client.post(UPLOAD_URL, files={"file": ("notes.txt", b"hello", "text/plain")})
    assert resp.status_code == 400


def test_upload_rejects_oversized_file(client):
    big_content = b"0" * (5 * 1024 * 1024 + 1)
    resp = client.post(UPLOAD_URL, files={"file": ("big.png", big_content, "image/png")})
    assert resp.status_code == 400


def test_submit_with_attachment_visible_in_session(client, monkeypatch, admin_auth_headers):
    _mock_escalated(monkeypatch)

    upload_resp = client.post(UPLOAD_URL, files={"file": ("photo.png", _TINY_PNG, "image/png")})
    url = upload_resp.json()["url"]

    submit_resp = client.post(SUBMIT_URL, json={
        "customer_id": "cust_attach",
        "channel": "web_chat",
        "message": "Sản phẩm bị lỗi, ảnh đính kèm",
        "attachment_url": url,
    })
    assert submit_resp.status_code == 200

    session_resp = client.get("/api/support/session/cust_attach")
    data = session_resp.json()
    customer_msg = next(m for m in data["messages"] if m["role"] == "user")
    assert customer_msg["attachment_url"] == url


def test_initial_attachment_stays_visible_in_full_history_after_followup(client, monkeypatch, admin_auth_headers, staff_auth_headers):
    """Bug thực tế: sau khi nhân viên tiếp nhận và khách gửi thêm 1 tin nhắn live
    (không kèm ảnh), ảnh đính kèm ở tin nhắn đầu tiên vẫn phải còn thấy được
    trong lịch sử hội thoại đầy đủ trả về cho Dashboard — không bị 1 field tóm
    tắt (mới nhất/đầu tiên) làm mất đi bối cảnh."""
    _mock_escalated(monkeypatch)

    upload_resp = client.post(UPLOAD_URL, files={"file": ("photo.png", _TINY_PNG, "image/png")})
    url = upload_resp.json()["url"]

    client.post(SUBMIT_URL, json={
        "customer_id": "cust_attach_followup",
        "channel": "web_chat",
        "message": "San pham bi loi, anh dinh kem",
        "attachment_url": url,
    })

    client.post(
        "/api/support/tickets/cust_attach_followup/accept",
        json={"staff_name": "Linh"},
        headers=staff_auth_headers,
    )

    # Mô phỏng đúng field mà ws.py ghi cho tin nhắn live của khách — không có
    # key attachment_url.
    asyncio.run(session_store_module.append_message("cust_attach_followup", {
        "sender_type": "customer",
        "content": "oke",
        "timestamp": "2026-07-31T13:30:00",
    }))

    tickets_resp = client.get("/api/support/tickets", headers=admin_auth_headers)
    ticket = next(t for t in tickets_resp.json() if t["id"] == "cust_attach_followup")

    # "message"/"attachment_url" (tóm tắt tin mới nhất, dùng cho preview danh
    # sách) đã đổi thành tin live, không còn ảnh — đúng như thiết kế.
    assert ticket["message"] == "oke"
    assert ticket["attachment_url"] is None

    # nhưng lịch sử đầy đủ "messages" vẫn còn cả tin đầu (kèm ảnh) lẫn tin live
    customer_messages = [m for m in ticket["messages"] if m["role"] == "user"]
    assert customer_messages[0]["content"] == "San pham bi loi, anh dinh kem"
    assert customer_messages[0]["attachment_url"] == url
    assert customer_messages[-1]["content"] == "oke"
