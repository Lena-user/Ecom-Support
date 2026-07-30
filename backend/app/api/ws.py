"""WebSocket endpoint — kênh real-time giữa /chat và /dashboard qua Redis Pub/Sub."""

import asyncio
import json
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis
from app.auth import decode_token
from app.config import settings

ws_router = APIRouter()


def get_redis():
    return aioredis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)


@ws_router.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    await websocket.accept()

    # Khách hàng ẩn danh kết nối không kèm token (vẫn được phép chat, không bắt buộc login).
    # Nhân viên/admin (Dashboard) kết nối kèm ?token=... để được phép gửi role="bot".
    token = websocket.query_params.get("token")
    payload = decode_token(token) if token else None
    is_staff = bool(payload and payload.get("role") in ("staff", "admin"))

    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"session_{session_id}")

    # Track this connection's identity so we can skip echo-back
    conn_id = id(websocket)

    async def reader():
        """Đọc message từ Redis Pub/Sub → forward tới WebSocket client."""
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    raw = message["data"]
                    if isinstance(raw, str):
                        # Skip echo: nếu message có sender_conn_id trùng với conn này thì bỏ qua
                        try:
                            parsed = json.loads(raw)
                            if parsed.get("_sender") == conn_id:
                                continue
                            # Xoá field internal trước khi gửi cho client
                            parsed.pop("_sender", None)
                            await websocket.send_text(json.dumps(parsed))
                        except (json.JSONDecodeError, TypeError):
                            await websocket.send_text(raw)
        except asyncio.CancelledError:
            # Task bị cancel khi client disconnect — thoát sạch
            return
        except Exception:
            return

    task = asyncio.create_task(reader())

    try:
        from app import session_store

        while True:
            data = await websocket.receive_text()

            try:
                msg_obj = json.loads(data)
            except json.JSONDecodeError:
                msg_obj = None

            # Chặn giả danh nhân viên: chỉ connection đã xác thực staff/admin
            # (kèm ?token= hợp lệ) mới được gửi role="bot".
            if msg_obj is not None and msg_obj.get("role") == "bot" and not is_staff:
                continue

            # Lưu message vào session history
            if msg_obj is not None and msg_obj.get("type") == "message":
                await session_store.append_message(session_id, {
                    "sender_type": "staff" if msg_obj.get("role") == "bot" else "customer",
                    "content": msg_obj.get("content", ""),
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                })

            # Publish vào Redis kèm _sender để reader() lọc echo
            if msg_obj is not None:
                msg_obj["_sender"] = conn_id
                await redis.publish(f"session_{session_id}", json.dumps(msg_obj))
            else:
                await redis.publish(f"session_{session_id}", data)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # Cleanup mọi trường hợp
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await pubsub.unsubscribe(f"session_{session_id}")
        await pubsub.aclose()
        await redis.aclose()
