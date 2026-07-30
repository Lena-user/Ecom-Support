"""Redis-backed session/ticket store — thay SESSIONS_DB in-memory để dữ liệu
không mất khi backend restart. Mỗi hàm mở 1 connection ngắn hạn (demo scope),
theo đúng style `_get_redis()` đã dùng trong routes.py.
"""

import json
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

_SESSION_KEY = "support:session:{customer_id}"
_INDEX_KEY = "support:sessions"


def _client() -> aioredis.Redis:
    return aioredis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)


async def get(customer_id: str) -> dict[str, Any] | None:
    r = _client()
    try:
        raw = await r.get(_SESSION_KEY.format(customer_id=customer_id))
        return json.loads(raw) if raw else None
    finally:
        await r.aclose()


async def save(customer_id: str, session: dict[str, Any]) -> None:
    r = _client()
    try:
        await r.set(_SESSION_KEY.format(customer_id=customer_id), json.dumps(session))
        await r.sadd(_INDEX_KEY, customer_id)
    finally:
        await r.aclose()


async def list_all() -> list[dict[str, Any]]:
    r = _client()
    try:
        ids = await r.smembers(_INDEX_KEY)
        if not ids:
            return []
        keys = [_SESSION_KEY.format(customer_id=cid) for cid in ids]
        raw_values = await r.mget(keys)
        return [json.loads(v) for v in raw_values if v]
    finally:
        await r.aclose()


async def append_message(customer_id: str, message: dict[str, Any]) -> None:
    """No-op nếu session chưa tồn tại — giữ đúng behavior guard cũ trong ws.py."""
    session = await get(customer_id)
    if session is None:
        return
    session.setdefault("messages", []).append(message)
    await save(customer_id, session)
