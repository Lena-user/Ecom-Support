"""Redis-backed log "khoảng trống kiến thức" — lưu lại câu hỏi mà AI đánh giá
không đủ căn cứ tài liệu để trả lời (needs_kb_review=True ở rag_respond), để
admin xem và chủ động bổ sung Knowledge Base. Cùng style module async với
session_store.py.
"""

import json
import time
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

_GAPS_KEY = "support:knowledge_gaps"
_MAX_GAPS = 200


def _client() -> aioredis.Redis:
    return aioredis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)


async def log_gap(message: str, reasoning: str, ticket_id: str, classification: str) -> None:
    r = _client()
    try:
        entry = json.dumps({
            "message": message,
            "reasoning": reasoning,
            "ticket_id": ticket_id,
            "classification": classification,
            "timestamp": time.time(),
        })
        await r.lpush(_GAPS_KEY, entry)
        await r.ltrim(_GAPS_KEY, 0, _MAX_GAPS - 1)
    finally:
        await r.aclose()


async def list_gaps() -> list[dict[str, Any]]:
    r = _client()
    try:
        raw_values = await r.lrange(_GAPS_KEY, 0, -1)
        return [json.loads(v) for v in raw_values]
    finally:
        await r.aclose()
