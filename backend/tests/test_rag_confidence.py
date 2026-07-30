"""Test cơ chế "Gemini tự đánh giá độ tin cậy" ở rag_respond — thay cho việc
chỉ dựa vào ngưỡng similarity để quyết định resolved/escalate.
"""

import types

from app.graph import nodes as nodes_module

SUBMIT_URL = "/api/support/submit"


class _StubQdrant:
    def __init__(self, results):
        self._results = results

    def search(self, **kwargs):
        return self._results


def _classify_info_inquiry():
    return {
        "classification": "info_inquiry",
        "priority": "low",
        "has_sufficient_info": True,
        "requires_human": False,
        "reasoning": "test",
    }


def test_rag_respond_routes_to_respond_when_gemini_confirms_sufficient_grounding(monkeypatch):
    """Unit test thuần cho rag_respond — có tài liệu khớp + Gemini nói đủ căn cứ
    → response dùng answer của Gemini, rag_documents có dữ liệu, after_rag → respond."""
    stub_doc = types.SimpleNamespace(
        payload={"id": "doc1", "source": "Chính sách đổi trả", "content": "Đổi trả trong 7 ngày."},
        score=0.91,
    )
    monkeypatch.setattr(nodes_module, "get_qdrant", lambda: _StubQdrant([stub_doc]))
    monkeypatch.setattr(nodes_module, "get_embedding", lambda text: [0.1, 0.2])
    monkeypatch.setattr(
        nodes_module,
        "generate_rag_response",
        lambda message, documents: {
            "answer": "Bạn có thể đổi trả trong 7 ngày.",
            "has_sufficient_grounding": True,
            "reasoning": "Tài liệu khớp trực tiếp với câu hỏi.",
        },
    )

    state = {"message": "Chính sách đổi trả như thế nào?", "embedding_vector": None}
    result = nodes_module.rag_respond(state)

    assert result["rag_has_sufficient_grounding"] is True
    assert result["needs_kb_review"] is False
    assert result["response"] == "Bạn có thể đổi trả trong 7 ngày."
    assert result["rag_documents"] == [
        {"id": "doc1", "source": "Chính sách đổi trả", "content": "Đổi trả trong 7 ngày.", "score": 0.91}
    ]
    assert nodes_module.after_rag(result) == "respond"


def test_rag_respond_routes_to_escalate_when_gemini_says_insufficient(monkeypatch):
    """Unit test thuần: dù có tài liệu (hoặc không), Gemini tự đánh giá không đủ
    căn cứ → phải escalate, escalation_reason chứa lý do của Gemini."""
    monkeypatch.setattr(nodes_module, "get_qdrant", lambda: _StubQdrant([]))
    monkeypatch.setattr(nodes_module, "get_embedding", lambda text: [0.1, 0.2])
    monkeypatch.setattr(
        nodes_module,
        "generate_rag_response",
        lambda message, documents: {
            "answer": "Xin lỗi, tôi chưa có đủ thông tin để trả lời chính xác.",
            "has_sufficient_grounding": False,
            "reasoning": "Không có tài liệu nào đề cập tới bảo hành pin.",
        },
    )

    state = {"message": "Chính sách bảo hành pin thế nào?", "embedding_vector": None}
    result = nodes_module.rag_respond(state)

    assert result["rag_has_sufficient_grounding"] is False
    assert result["needs_kb_review"] is True
    assert "Không có tài liệu nào đề cập tới bảo hành pin" in result["escalation_reason"]
    assert nodes_module.after_rag(result) == "escalate"


def test_insufficient_grounding_escalates_via_api_and_logs_knowledge_gap(client, monkeypatch, admin_auth_headers):
    """Integration test qua /submit: escalate đúng status + lý do, và câu hỏi
    được ghi vào 'khoảng trống kiến thức' để admin xem qua /knowledge-gaps."""
    monkeypatch.setattr(nodes_module, "classify_message", lambda message, channel: _classify_info_inquiry())
    monkeypatch.setattr(
        nodes_module,
        "generate_rag_response",
        lambda message, documents: {
            "answer": "Xin lỗi, tôi chưa có đủ thông tin để trả lời chính xác câu này.",
            "has_sufficient_grounding": False,
            "reasoning": "Không có tài liệu nào đề cập tới bảo hành pin.",
        },
    )

    resp = client.post(
        SUBMIT_URL,
        json={
            "customer_id": "cust_kb_gap",
            "channel": "web_chat",
            "message": "Chính sách bảo hành pin thế nào?",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "PENDING_ESCALATION"
    assert "Không có tài liệu nào đề cập tới bảo hành pin" in data["escalation_reason"]

    gaps_resp = client.get("/api/support/knowledge-gaps", headers=admin_auth_headers)
    assert gaps_resp.status_code == 200
    gaps = gaps_resp.json()
    assert len(gaps) == 1
    assert gaps[0]["message"] == "Chính sách bảo hành pin thế nào?"


def test_sufficient_grounding_does_not_log_knowledge_gap(client, monkeypatch, admin_auth_headers):
    monkeypatch.setattr(nodes_module, "classify_message", lambda message, channel: _classify_info_inquiry())
    monkeypatch.setattr(
        nodes_module,
        "generate_rag_response",
        lambda message, documents: {
            "answer": "Đổi trả trong vòng 7 ngày.",
            "has_sufficient_grounding": True,
            "reasoning": "",
        },
    )

    resp = client.post(
        SUBMIT_URL,
        json={"customer_id": "cust_no_gap", "channel": "web_chat", "message": "Chính sách đổi trả thế nào?"},
    )
    assert resp.json()["status"] == "RESOLVED"

    gaps_resp = client.get("/api/support/knowledge-gaps", headers=admin_auth_headers)
    assert gaps_resp.json() == []
