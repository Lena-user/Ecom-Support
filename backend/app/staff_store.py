"""Redis-backed staff/admin account store — thay `USERS` hardcode trong auth.py
để Admin có thể thêm/xoá tài khoản nhân viên thật qua UI. Cùng style module
async với session_store.py.
"""

import json
import time
from typing import Any, Literal

import bcrypt
import redis.asyncio as aioredis

from app.config import settings

_STAFF_KEY = "support:staff:{email}"
_INDEX_KEY = "support:staff_emails"

Role = Literal["admin", "staff"]

# 3 tài khoản demo gốc — chỉ dùng để seed lần đầu, không hardcode xác thực nữa
_DEFAULT_ACCOUNTS = [
    {"email": "admin@demo.com", "name": "Admin", "role": "admin"},
    {"email": "staff@demo.com", "name": "Linh Nguyễn", "role": "staff"},
    {"email": "staff2@demo.com", "name": "Minh Trần", "role": "staff"},
]
_DEFAULT_PASSWORD = "123"


def _client() -> aioredis.Redis:
    return aioredis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


async def get(email: str) -> dict[str, Any] | None:
    r = _client()
    try:
        raw = await r.get(_STAFF_KEY.format(email=email))
        return json.loads(raw) if raw else None
    finally:
        await r.aclose()


async def list_all() -> list[dict[str, Any]]:
    r = _client()
    try:
        emails = await r.smembers(_INDEX_KEY)
        if not emails:
            return []
        raw_values = await r.mget([_STAFF_KEY.format(email=e) for e in emails])
        return [json.loads(v) for v in raw_values if v]
    finally:
        await r.aclose()


async def create(email: str, name: str, role: Role, password: str) -> dict[str, Any]:
    if await get(email) is not None:
        raise ValueError(f"Email đã tồn tại: {email}")

    record = {
        "email": email,
        "name": name,
        "role": role,
        "password_hash": _hash_password(password),
        "created_at": time.time(),
    }
    r = _client()
    try:
        await r.set(_STAFF_KEY.format(email=email), json.dumps(record))
        await r.sadd(_INDEX_KEY, email)
    finally:
        await r.aclose()
    return record


async def delete(email: str) -> None:
    r = _client()
    try:
        await r.delete(_STAFF_KEY.format(email=email))
        await r.srem(_INDEX_KEY, email)
    finally:
        await r.aclose()


async def seed_defaults() -> None:
    """Idempotent — seed 3 tài khoản demo gốc nếu store đang rỗng, để hành vi
    login cũ không đổi sau khi chuyển từ USERS hardcode sang Redis."""
    existing = await list_all()
    if existing:
        return
    for account in _DEFAULT_ACCOUNTS:
        await create(
            email=account["email"],
            name=account["name"],
            role=account["role"],
            password=_DEFAULT_PASSWORD,
        )
