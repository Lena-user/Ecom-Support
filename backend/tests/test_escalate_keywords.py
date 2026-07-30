"""Test từ khoá escalate thủ công (Admin > Cấu hình AI) — phải ép escalate
dù Gemini phân loại là info_inquiry (nội dung không phải khiếu nại rõ ràng)."""

from app.graph import nodes as nodes_module

SUBMIT_URL = "/api/support/submit"


def _mock_info_inquiry(monkeypatch):
    monkeypatch.setattr(
        nodes_module,
        "classify_message",
        lambda message, channel: {
            "classification": "info_inquiry",
            "priority": "low",
            "has_sufficient_info": True,
            "requires_human": False,
            "reasoning": "test",
        },
    )
    monkeypatch.setattr(
        nodes_module,
        "generate_rag_response",
        lambda message, documents: {"answer": "Câu trả lời mẫu.", "has_sufficient_grounding": True, "reasoning": ""},
    )


def test_message_with_configured_keyword_forces_escalation(client, monkeypatch):
    _mock_info_inquiry(monkeypatch)

    resp = client.post(
        SUBMIT_URL,
        json={
            "customer_id": "cust_keyword",
            "channel": "web_chat",
            "message": "Nếu không giải quyết tôi sẽ kiện các anh ra toà",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["classification"] == "info_inquiry"  # Gemini vẫn phân loại như vậy
    assert data["status"] == "PENDING_ESCALATION"  # nhưng bị ép escalate vì từ khoá cấu hình sẵn
    assert "kiện" in data["escalation_reason"]


def test_message_without_configured_keyword_is_not_escalated(client, monkeypatch):
    _mock_info_inquiry(monkeypatch)

    resp = client.post(
        SUBMIT_URL,
        json={
            "customer_id": "cust_no_keyword",
            "channel": "web_chat",
            "message": "Cho tôi hỏi thời gian giao hàng nội thành mất bao lâu?",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "RESOLVED"
