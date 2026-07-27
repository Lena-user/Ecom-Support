"""FastAPI entrypoint — khởi tạo app, kết nối Redis/Qdrant, expose /health."""

from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import QdrantClient

from app.api.routes import router as support_router
from app.config import settings


# ---------- Shared clients (khởi tạo khi startup) ---------- #
redis_client: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Quản lý lifecycle: mở kết nối khi startup, đóng khi shutdown."""
    global redis_client

    # Startup — kết nối Redis
    redis_client = aioredis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        decode_responses=True,
    )

    yield

    # Shutdown — đóng kết nối
    if redis_client:
        await redis_client.aclose()


# ---------- FastAPI app ---------- #
app = FastAPI(
    title="E-commerce Support Automation",
    description="Hệ thống chăm sóc khách hàng tự động cho sàn TMĐT",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — cho phép frontend (Next.js) gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Demo scope — production cần restrict
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Router đăng ký ---------- #
app.include_router(support_router)


# ---------- Routes ---------- #
@app.get("/health")
async def health_check():
    """Kiểm tra sức khỏe hệ thống: app + Redis + Qdrant."""
    status = {"app": "ok", "redis": "error", "qdrant": "error"}

    # Check Redis
    try:
        if redis_client:
            pong = await redis_client.ping()
            status["redis"] = "ok" if pong else "error"
    except Exception as e:
        status["redis"] = f"error: {e}"

    # Check Qdrant
    try:
        from app.qdrant import get_qdrant
        client = get_qdrant()
        info = client.get_collections()
        status["qdrant"] = "ok"
    except Exception as e:
        status["qdrant"] = f"error: {e}"

    # Healthy chỉ khi tất cả service đều ok
    all_ok = all(v == "ok" for v in status.values())

    return {
        "healthy": all_ok,
        "services": status,
    }
