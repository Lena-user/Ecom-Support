"""Integration test cho POST /api/support/submit — mock Gemini (classify/RAG/embedding)
và Qdrant qua fixture isolate_external_services trong conftest.py, chạy toàn bộ
pipeline LangGraph thật (workflow.invoke) không cần gọi service bên ngoài.

Đây là bản tự động hoá của các kịch bản thủ công trong test_cases.sh cũ.
"""

import pytest

from app.auth import create_access_token
from app.graph import nodes as nodes_module

SUBMIT_URL = "/api/support/submit"


def _classify_result(classification, priority="medium", has_sufficient_info=True, requires_human=False):
    return {
        "classification": classification,
        "priority": priority,
        "has_sufficient_info": has_sufficient_info,
        "requires_human": requires_human,
        "reasoning": "test",
    }


def _rag_result(answer="Câu trả lời mẫu.", has_sufficient_grounding=True, reasoning=""):
    return {"answer": answer, "has_sufficient_grounding": has_sufficient_grounding, "reasoning": reasoning}


CLASSIFY_CASES = [
    pytest.param(_classify_result("info_inquiry", "low"), "RESOLVED", "info_inquiry", id="info_inquiry"),
    pytest.param(_classify_result("complaint", "high", requires_human=True), "PENDING_ESCALATION", "complaint", id="complaint"),
    pytest.param(_classify_result("technical", "medium"), "RESOLVED", "technical", id="technical"),
    pytest.param(_classify_result("payment", "high", requires_human=True), "PENDING_ESCALATION", "payment", id="payment"),
    pytest.param(_classify_result("emergency", "critical", requires_human=True), "PENDING_ESCALATION", "emergency", id="emergency"),
    pytest.param(_classify_result("spam", "low"), "RESOLVED", "spam", id="spam"),
    pytest.param(_classify_result("missing_info", "medium", has_sufficient_info=False), "RESOLVED", "missing_info", id="missing_info"),
    pytest.param(_classify_result("human_requested", "medium", requires_human=True), "PENDING_ESCALATION", "human_requested", id="human_requested"),
]


@pytest.mark.parametrize("classify_result, expected_status, expected_classification", CLASSIFY_CASES)
def test_submit_routes_by_classification(client, monkeypatch, classify_result, expected_status, expected_classification):
    monkeypatch.setattr(nodes_module, "classify_message", lambda message, channel: classify_result)
    monkeypatch.setattr(nodes_module, "generate_rag_response", lambda message, documents: _rag_result())

    resp = client.post(
        SUBMIT_URL,
        json={
            "customer_id": f"cust_{expected_classification}",
            "channel": "web_chat",
            "message": "Nội dung yêu cầu test",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["classification"] == expected_classification
    assert data["status"] == expected_status
    assert data["response"]


def test_duplicate_message_short_circuits_classification(client, monkeypatch):
    """Gửi đúng 1 câu 2 lần cho cùng khách hàng: lần 2 phải bị chặn ở bước
    duplicate-check (Qdrant) và KHÔNG được gọi lại classify_message."""
    call_count = {"n": 0}

    def fake_classify(message, channel):
        call_count["n"] += 1
        return _classify_result("info_inquiry", "low")

    monkeypatch.setattr(nodes_module, "classify_message", fake_classify)
    monkeypatch.setattr(nodes_module, "generate_rag_response", lambda message, documents: _rag_result())

    payload = {"customer_id": "cust_dup", "channel": "web_chat", "message": "Câu hỏi lặp lại y hệt"}

    first = client.post(SUBMIT_URL, json=payload)
    assert first.status_code == 200
    assert first.json()["is_duplicate"] is False
    assert call_count["n"] == 1

    second = client.post(SUBMIT_URL, json=payload)
    assert second.status_code == 200
    assert second.json()["is_duplicate"] is True
    assert call_count["n"] == 1  # classify không chạy lại vì đã dừng ở duplicate-check


def test_tickets_endpoint_lists_created_sessions(client, monkeypatch, staff_auth_headers):
    monkeypatch.setattr(nodes_module, "classify_message", lambda message, channel: _classify_result("info_inquiry", "low"))
    monkeypatch.setattr(nodes_module, "generate_rag_response", lambda message, documents: _rag_result())

    client.post(SUBMIT_URL, json={"customer_id": "cust_list", "channel": "web_chat", "message": "Xin chào"})

    resp = client.get("/api/support/tickets", headers=staff_auth_headers)
    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()]
    assert "cust_list" in ids


def test_stats_endpoint_reflects_submitted_requests(client, monkeypatch, admin_auth_headers):
    monkeypatch.setattr(nodes_module, "classify_message", lambda message, channel: _classify_result("complaint", "high", requires_human=True))
    monkeypatch.setattr(nodes_module, "generate_rag_response", lambda message, documents: _rag_result())

    client.post(SUBMIT_URL, json={"customer_id": "cust_stats", "channel": "web_chat", "message": "Hàng bị lỗi"})

    resp = client.get("/api/support/stats", headers=admin_auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_requests"] >= 1
    assert data["by_classification"].get("complaint", 0) >= 1


def test_stats_counts_escalated_then_closed_ticket_as_handled_by_human(client, monkeypatch, admin_auth_headers, staff_auth_headers):
    """Bug thực tế: ticket 'payment' (luôn phải escalate theo thiết kế) sau khi
    nhân viên tiếp nhận + đóng ca thì status cũng thành RESOLVED giống hệt ticket
    AI tự xử lý — nếu /stats chỉ nhìn status cuối sẽ đếm nhầm thành "AI tự xử lý"
    thay vì "chuyển người", dù thực tế chưa từng có ticket payment nào AI tự
    trả lời được (payment luôn bị ép escalate)."""
    monkeypatch.setattr(nodes_module, "classify_message", lambda message, channel: _classify_result("payment", "high", requires_human=True))
    monkeypatch.setattr(nodes_module, "generate_rag_response", lambda message, documents: _rag_result())

    customer_id = "cust_payment_closed"
    submit_resp = client.post(SUBMIT_URL, json={"customer_id": customer_id, "channel": "web_chat", "message": "Hoàn tiền đơn hàng của tôi"})
    assert submit_resp.json()["status"] == "PENDING_ESCALATION"

    client.post(f"/api/support/tickets/{customer_id}/accept", json={"staff_name": "Linh"}, headers=staff_auth_headers)
    client.post(f"/api/support/tickets/{customer_id}/close", headers=staff_auth_headers)

    tickets_resp = client.get("/api/support/tickets", headers=staff_auth_headers)
    ticket = next(t for t in tickets_resp.json() if t["id"] == customer_id)
    assert ticket["status"] == "RESOLVED"  # đã đóng ca, status hiện tại là RESOLVED

    stats_resp = client.get("/api/support/stats", headers=admin_auth_headers)
    data = stats_resp.json()
    payment_bucket = data["by_type_status"]["payment"]
    assert payment_bucket["escalate"] >= 1
    assert payment_bucket["auto"] == 0  # KHÔNG được tính là AI tự xử lý
    assert data["escalated_count"] >= 1


def test_accept_ticket_rejects_when_not_pending_escalation(client, monkeypatch, staff_auth_headers):
    """accept_ticket() trước đây chỉ chặn khi ticket ĐÃ ở HUMAN_HANDLING, không
    kiểm tra ticket có thực sự đang PENDING_ESCALATION hay không — nghĩa là gọi
    thẳng API (hoặc race condition 2 tab bấm gần như cùng lúc) có thể ép 1
    ticket đang RESOLVED nhảy thẳng lên HUMAN_HANDLING một cách bất thường."""
    monkeypatch.setattr(nodes_module, "classify_message", lambda message, channel: _classify_result("info_inquiry", "low"))
    monkeypatch.setattr(nodes_module, "generate_rag_response", lambda message, documents: _rag_result())

    customer_id = "cust_accept_guard"
    submit_resp = client.post(SUBMIT_URL, json={"customer_id": customer_id, "channel": "web_chat", "message": "Chính sách đổi trả?"})
    assert submit_resp.json()["status"] == "RESOLVED"  # info_inquiry tự trả lời xong, chưa từng escalate

    accept_resp = client.post(
        f"/api/support/tickets/{customer_id}/accept",
        json={"staff_name": "Linh Nguyễn"},
        headers=staff_auth_headers,
    )
    assert "error" in accept_resp.json()

    tickets_resp = client.get("/api/support/tickets", headers=staff_auth_headers)
    ticket = next(t for t in tickets_resp.json() if t["id"] == customer_id)
    assert ticket["status"] == "RESOLVED"  # không bị đẩy nhầm lên HUMAN_HANDLING


def test_only_one_staff_can_accept_the_same_ticket(client, monkeypatch, staff_auth_headers):
    """2 nhân viên cùng bấm "Tiếp nhận" 1 ticket gần như đồng thời — chỉ người
    đầu tiên được thành công, người sau phải nhận lỗi rõ ràng (không phải cả 2
    đều "thành công" rồi âm thầm đè lên nhau, mất dấu ai thực sự đang xử lý)."""
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
    other_staff_headers = {"Authorization": f"Bearer {create_access_token(email='staff2@demo.com', role='staff', name='Minh Trần')}"}

    customer_id = "cust_accept_race"
    client.post(SUBMIT_URL, json={"customer_id": customer_id, "channel": "web_chat", "message": "Hàng bị lỗi"})

    first = client.post(f"/api/support/tickets/{customer_id}/accept", json={"staff_name": "Linh Nguyễn"}, headers=staff_auth_headers)
    second = client.post(f"/api/support/tickets/{customer_id}/accept", json={"staff_name": "Minh Trần"}, headers=other_staff_headers)

    assert first.json().get("success") is True
    assert "error" in second.json()
    assert "Linh Nguyễn" in second.json()["error"]

    tickets_resp = client.get("/api/support/tickets", headers=staff_auth_headers)
    ticket = next(t for t in tickets_resp.json() if t["id"] == customer_id)
    assert ticket["staff_assigned"] == "Linh Nguyễn"


def test_stats_counts_each_message_in_same_session_as_separate_request(client, monkeypatch, admin_auth_headers):
    """Nhiều tin nhắn khác nhau trong cùng 1 session (kể cả sau khi từng RESOLVED
    rồi khách nhắn tiếp) phải được tính là nhiều request riêng biệt, không gộp
    chung thành 1 — bug đã gặp thực tế: log bị xoá mỗi vòng resolved→reopen."""
    monkeypatch.setattr(nodes_module, "classify_message", lambda message, channel: _classify_result("info_inquiry", "low"))
    monkeypatch.setattr(nodes_module, "generate_rag_response", lambda message, documents: _rag_result())

    customer_id = "cust_multi_request"
    for msg in ["Chính sách đổi trả hàng như thế nào?", "Phí vận chuyển tính ra sao?", "Cảm ơn bạn"]:
        resp = client.post(SUBMIT_URL, json={"customer_id": customer_id, "channel": "web_chat", "message": msg})
        assert resp.json()["status"] == "RESOLVED"

    session_resp = client.get(f"/api/support/session/{customer_id}")
    assert len(session_resp.json()["messages"]) == 6  # 3 khách + 3 bot

    stats_resp = client.get("/api/support/stats", headers=admin_auth_headers)
    data = stats_resp.json()
    matching_requests = data["by_classification"].get("info_inquiry", 0)
    assert matching_requests >= 3
