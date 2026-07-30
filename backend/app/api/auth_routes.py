"""API xác thực — đăng nhập, cấp JWT."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.auth import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    role: str
    name: str


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest):
    user = verify_password(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")
    token = create_access_token(email=payload.email, role=user["role"], name=user["name"])
    return LoginResponse(access_token=token, role=user["role"], name=user["name"])
