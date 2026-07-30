"""Redis-backed cấu hình AI runtime (similarity threshold, duplicate window,
escalate keywords). Dùng client Redis đồng bộ (không phải redis.asyncio) vì
được gọi từ bên trong các LangGraph node trong app/graph/nodes.py, vốn là
hàm sync chạy qua workflow.invoke().
"""

import json

import redis as sync_redis

from app.config import settings

_SETTINGS_KEY = "support:ai_settings"

DEFAULT_SETTINGS = {
    "similarity_threshold": 0.65,
    "duplicate_window_hours": 24,
    "escalate_keywords": ["kiện", "pháp luật", "báo chí", "lừa đảo"],
}


def _client() -> sync_redis.Redis:
    return sync_redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)


def get_settings() -> dict:
    r = _client()
    try:
        raw = r.get(_SETTINGS_KEY)
        if not raw:
            return dict(DEFAULT_SETTINGS)
        data = json.loads(raw)
        return {**DEFAULT_SETTINGS, **data}
    finally:
        r.close()


def save_settings(data: dict) -> dict:
    merged = {**get_settings(), **data}
    r = _client()
    try:
        r.set(_SETTINGS_KEY, json.dumps(merged))
    finally:
        r.close()
    return merged
