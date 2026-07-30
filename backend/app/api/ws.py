"""WebSocket endpoint — kênh real-time giữa /chat và /dashboard qua Redis Pub/Sub."""

import asyncio
import json
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis
from app.config import settings

ws_router = APIRouter()


def get_redis():
    return aioredis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)


@ws_router.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    await websocket.accept()

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
        from app.api.routes import SESSIONS_DB

        while True:
            data = await websocket.receive_text()

            # Lưu message vào session history
            try:
                msg_obj = json.loads(data)
                if msg_obj.get("type") == "message" and session_id in SESSIONS_DB:
                    SESSIONS_DB[session_id]["messages"].append({
                        "sender_type": "staff" if msg_obj.get("role") == "bot" else "customer",
                        "content": msg_obj.get("content", ""),
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                    })
            except (json.JSONDecodeError, KeyError):
                pass

            # Publish vào Redis kèm _sender để reader() lọc echo
            try:
                enriched = json.loads(data)
                enriched["_sender"] = conn_id
                await redis.publish(f"session_{session_id}", json.dumps(enriched))
            except (json.JSONDecodeError, TypeError):
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
