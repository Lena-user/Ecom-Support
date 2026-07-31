"""Auth: JWT bearer token + xác thực mật khẩu bằng bcrypt.

Tài khoản staff/admin được lưu động trong Redis (app/staff_store.py) —
seed sẵn 3 tài khoản demo lúc backend khởi động (xem main.py), Admin có
thể thêm/xoá tài khoản thật qua UI.
"""

import time
from typing import Literal

import bcrypt
import jwt
from fastapi import HTTPException, Request

from app import staff_store
from app.config import settings

Role = Literal["admin", "staff"]

ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 8 * 3600


async def verify_password(email: str, password: str) -> dict | None:
    """Trả về thông tin user nếu email/password hợp lệ, None nếu không."""
    user = await staff_store.get(email)
    if not user:
        return None
    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return None
    return user


def create_access_token(email: str, role: str, name: str) -> str:
    now = int(time.time())
    payload = {"sub": email, "role": role, "name": name, "iat": now, "exp": now + TOKEN_TTL_SECONDS}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def _extract_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    return header[len("bearer "):]


def require_role(*roles: Role):
    """FastAPI dependency — chỉ cho qua nếu token hợp lệ và role nằm trong `roles`."""

    def dependency(request: Request) -> dict:
        token = _extract_token(request)
        if not token:
            raise HTTPException(status_code=401, detail="Thiếu token xác thực")
        payload = decode_token(token)
        if payload is None:
            raise HTTPException(status_code=401, detail="Token không hợp lệ hoặc đã hết hạn")
        if payload.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Không đủ quyền truy cập")
        return payload

    return dependency
