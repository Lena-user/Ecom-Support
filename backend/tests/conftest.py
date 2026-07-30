"""Fixtures dùng chung: mock Qdrant + Redis (session_store/settings_store) +
embedding để test không cần service thật chạy."""

import pytest
from fastapi.testclient import TestClient

import app.knowledge_gaps as knowledge_gaps_module
import app.session_store as session_store_module
import app.settings_store as settings_store_module
from app.api import routes as routes_module
from app.auth import create_access_token
from app.graph import nodes as nodes_module
from app.main import app


class _FakeScoredPoint:
    def __init__(self, id_, score, payload):
        self.id = id_
        self.score = score
        self.payload = payload


class _FakeRecord:
    def __init__(self, id_, payload):
        self.id = id_
        self.payload = payload


class FakeQdrantClient:
    """Thay thế QdrantClient thật — lưu điểm trong bộ nhớ theo collection_name,
    generic để phục vụ cả 'tickets' (duplicate check) và 'knowledge_base' (RAG + KB CRUD)."""

    def __init__(self):
        self._collections: dict[str, list[dict]] = {}

    def _points(self, collection_name: str) -> list[dict]:
        return self._collections.setdefault(collection_name, [])

    @staticmethod
    def _matches_filter(point: dict, query_filter) -> bool:
        for condition in query_filter.must:
            value = point["payload"].get(condition.key)
            if condition.match is not None and value != condition.match.value:
                return False
            if condition.range is not None:
                rng = condition.range
                if rng.gte is not None and not (value is not None and value >= rng.gte):
                    return False
                if rng.lte is not None and not (value is not None and value <= rng.lte):
                    return False
        return True

    def search(self, collection_name, query_vector, query_filter=None, limit=1, score_threshold=None, **kwargs):
        results = []
        for point in self._points(collection_name):
            if query_filter is not None and not self._matches_filter(point, query_filter):
                continue
            if point["vector"] == query_vector:
                results.append(_FakeScoredPoint(point["id"], 1.0, point["payload"]))
        if score_threshold is not None:
            results = [r for r in results if r.score >= score_threshold]
        return results[:limit]

    def upsert(self, collection_name, points):
        existing = self._points(collection_name)
        for p in points:
            existing[:] = [pt for pt in existing if pt["id"] != p.id]
            existing.append({"id": p.id, "vector": p.vector, "payload": p.payload})

    def scroll(self, collection_name, scroll_filter=None, limit=10, with_payload=True, with_vectors=False, **kwargs):
        points = self._points(collection_name)
        records = [_FakeRecord(p["id"], p["payload"]) for p in points[:limit]]
        return records, None

    def delete(self, collection_name, points_selector, **kwargs):
        ids_to_remove = set(points_selector) if isinstance(points_selector, list) else set()
        existing = self._points(collection_name)
        existing[:] = [pt for pt in existing if pt["id"] not in ids_to_remove]


def _fake_get_embedding(text: str) -> list[float]:
    """Vector giả định — cùng text luôn ra cùng vector, khác text ra vector khác."""
    return [float(sum(text.encode()))]


@pytest.fixture(autouse=True)
def isolate_external_services(monkeypatch):
    """Mock Qdrant, session_store (Redis) và settings_store (Redis) cho mọi test."""
    fake_qdrant = FakeQdrantClient()
    monkeypatch.setattr(nodes_module, "get_qdrant", lambda: fake_qdrant)
    monkeypatch.setattr(nodes_module, "get_embedding", _fake_get_embedding)
    monkeypatch.setattr(routes_module, "get_qdrant", lambda: fake_qdrant)
    monkeypatch.setattr(routes_module, "get_embedding", _fake_get_embedding)

    sessions: dict[str, dict] = {}

    async def fake_get(customer_id):
        return sessions.get(customer_id)

    async def fake_save(customer_id, session):
        sessions[customer_id] = session

    async def fake_list_all():
        return list(sessions.values())

    async def fake_append_message(customer_id, message):
        session = sessions.get(customer_id)
        if session is None:
            return
        session.setdefault("messages", []).append(message)

    monkeypatch.setattr(session_store_module, "get", fake_get)
    monkeypatch.setattr(session_store_module, "save", fake_save)
    monkeypatch.setattr(session_store_module, "list_all", fake_list_all)
    monkeypatch.setattr(session_store_module, "append_message", fake_append_message)

    settings_state = dict(settings_store_module.DEFAULT_SETTINGS)

    def fake_get_settings():
        return dict(settings_state)

    def fake_save_settings(data):
        settings_state.update(data)
        return dict(settings_state)

    monkeypatch.setattr(settings_store_module, "get_settings", fake_get_settings)
    monkeypatch.setattr(settings_store_module, "save_settings", fake_save_settings)

    gaps: list[dict] = []

    async def fake_log_gap(message, reasoning, ticket_id, classification):
        gaps.append({
            "message": message,
            "reasoning": reasoning,
            "ticket_id": ticket_id,
            "classification": classification,
            "timestamp": 0,
        })

    async def fake_list_gaps():
        return list(gaps)

    monkeypatch.setattr(knowledge_gaps_module, "log_gap", fake_log_gap)
    monkeypatch.setattr(knowledge_gaps_module, "list_gaps", fake_list_gaps)

    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_auth_headers():
    token = create_access_token(email="admin@demo.com", role="admin", name="Admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def staff_auth_headers():
    token = create_access_token(email="staff@demo.com", role="staff", name="Linh Nguyễn")
    return {"Authorization": f"Bearer {token}"}
