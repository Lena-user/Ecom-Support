"""Test CSAT — khách hàng đánh giá 👍/👎 sau khi ticket resolved."""

from app.graph import nodes as nodes_module

SUBMIT_URL = "/api/support/submit"


def _mock_resolved_response(monkeypatch):
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


def test_rate_ticket_updates_stats(client, monkeypatch, admin_auth_headers):
    _mock_resolved_response(monkeypatch)
    client.post(SUBMIT_URL, json={"customer_id": "cust_csat", "channel": "web_chat", "message": "Chính sách đổi trả?"})

    rate_resp = client.post("/api/support/tickets/cust_csat/rate", json={"rating": "up"})
    assert rate_resp.status_code == 200

    stats_resp = client.get("/api/support/stats", headers=admin_auth_headers)
    data = stats_resp.json()
    assert data["csat_positive"] >= 1
    assert data["csat_total"] >= 1


def test_rate_ticket_negative(client, monkeypatch, admin_auth_headers):
    _mock_resolved_response(monkeypatch)
    client.post(SUBMIT_URL, json={"customer_id": "cust_csat_down", "channel": "web_chat", "message": "Hỏi gì đó"})

    rate_resp = client.post("/api/support/tickets/cust_csat_down/rate", json={"rating": "down"})
    assert rate_resp.status_code == 200

    stats_resp = client.get("/api/support/stats", headers=admin_auth_headers)
    assert stats_resp.json()["csat_negative"] >= 1


def test_rate_nonexistent_session_returns_error(client):
    resp = client.post("/api/support/tickets/khong-ton-tai/rate", json={"rating": "up"})
    assert resp.status_code == 200
    assert resp.json().get("error") == "Session not found"


def test_rate_invalid_value_rejected(client, monkeypatch):
    _mock_resolved_response(monkeypatch)
    client.post(SUBMIT_URL, json={"customer_id": "cust_csat_invalid", "channel": "web_chat", "message": "abc"})
    resp = client.post("/api/support/tickets/cust_csat_invalid/rate", json={"rating": "meh"})
    assert resp.status_code == 422
