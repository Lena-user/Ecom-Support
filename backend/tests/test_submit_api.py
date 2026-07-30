"""Integration test cho POST /api/support/submit — mock Gemini (classify/RAG/embedding)
và Qdrant qua fixture isolate_external_services trong conftest.py, chạy toàn bộ
pipeline LangGraph thật (workflow.invoke) không cần gọi service bên ngoài.

Đây là bản tự động hoá của các kịch bản thủ công trong test_cases.sh cũ.
"""

import pytest

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
    assert data["escalated_count"] >= 1
