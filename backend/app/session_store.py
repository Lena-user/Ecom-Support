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


async def try_accept(customer_id: str, staff_name: str) -> tuple[str, dict[str, Any] | None]:
    """Chuyển session sang HUMAN_HANDLING một cách NGUYÊN TỬ (Redis WATCH/MULTI/
    EXEC) — tránh race condition khi 2 nhân viên bấm "Tiếp nhận" gần như đồng
    thời: nếu chỉ đọc-rồi-ghi thường (get() + save()) thì cả 2 request đều có
    thể đọc được status PENDING_ESCALATION trước khi request nào kịp ghi xong,
    dẫn đến cả 2 đều nhận phản hồi "thành công" nhưng người ghi sau âm thầm đè
    mất người ghi trước. WATCH đảm bảo nếu key bị đổi giữa lúc đọc và lúc ghi
    (bởi request khác) thì EXEC sẽ thất bại, request đó phải đọc lại và thấy
    đúng trạng thái mới nhất để trả lời chính xác.

    Trả về (kết quả, session):
    - ("ok", session): tiếp nhận thành công.
    - ("not_found", None): session không tồn tại.
    - ("already_handling", session): đã có người khác nhận trước.
    - ("not_pending", session): ticket không ở trạng thái chờ tiếp nhận.
    """
    r = _client()
    key = _SESSION_KEY.format(customer_id=customer_id)
    try:
        async with r.pipeline(transaction=True) as pipe:
            while True:
                await pipe.watch(key)
                raw = await pipe.get(key)
                session = json.loads(raw) if raw else None

                if session is None:
                    await pipe.unwatch()
                    return "not_found", None
                if session["status"] == "HUMAN_HANDLING":
                    await pipe.unwatch()
                    return "already_handling", session
                if session["status"] != "PENDING_ESCALATION":
                    await pipe.unwatch()
                    return "not_pending", session

                session["status"] = "HUMAN_HANDLING"
                session["staff_assigned"] = staff_name
                session.setdefault("handled_by", []).append(staff_name)

                pipe.multi()
                pipe.set(key, json.dumps(session))
                try:
                    await pipe.execute()
                    return "ok", session
                except aioredis.WatchError:
                    continue  # key vừa bị đổi bởi request khác — đọc lại rồi thử tiếp
    finally:
        await r.aclose()
