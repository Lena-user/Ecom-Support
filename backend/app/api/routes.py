"""API routes — endpoint tiếp nhận yêu cầu hỗ trợ."""

import json
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter
from app.graph.workflow import workflow
from app.models.schemas import SupportRequest, SupportResponse

router = APIRouter(prefix="/api/support", tags=["support"])

# ── In-Memory Session DB ─────────────────────────────────────────────
# Keyed by customer_id (= session_id in this demo).
# Field names match what the frontend Ticket interface expects.
SESSIONS_DB: Dict[str, Dict[str, Any]] = {}


def _get_redis():
    """Tạo 1 Redis client ngắn hạn (demo scope)."""
    import redis.asyncio as aioredis
    from app.config import settings
    return aioredis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)


def _serialize_session(s: Dict[str, Any]) -> Dict[str, Any]:
    """Chuyển session dict → format mà Frontend Ticket interface chờ đợi."""
    latest_msg = ""
    for m in reversed(s.get("messages", [])):
        if m.get("sender_type") == "customer":
            latest_msg = m.get("content", "")
            break
    return {
        "id": s["id"],
        "customer": s["customer"],
        "status": s["status"],
        "priority": s.get("priority", ""),
        "type": s.get("type", ""),
        "createdAt": s.get("createdAt", ""),
        "staff_assigned": s.get("staff_assigned"),
        "log": s.get("log", []),
        "message": latest_msg,
        "escalation_reason": s.get("escalation_reason", ""),
    }


# ── GET /tickets ──────────────────────────────────────────────────────
@router.get("/tickets")
async def get_tickets():
    """Trả danh sách sessions cho Staff Dashboard (mới nhất lên đầu)."""
    items = [_serialize_session(s) for s in SESSIONS_DB.values()]
    items.sort(key=lambda x: x["createdAt"], reverse=True)
    return items


# ── GET /session/{customer_id} ────────────────────────────────────────
@router.get("/session/{customer_id}")
async def get_session(customer_id: str):
    """Khôi phục session cho khách hàng khi quay lại trang chat.
    
    Trả về trạng thái session + toàn bộ lịch sử tin nhắn.
    """
    session = SESSIONS_DB.get(customer_id)
    if not session:
        return {"exists": False}

    # Chuyển messages → format frontend hiểu (role: user/bot)
    chat_messages = []
    for m in session.get("messages", []):
        sender = m.get("sender_type", "")
        role = "user" if sender == "customer" else "bot"
        chat_messages.append({
            "role": role,
            "content": m.get("content", ""),
        })

    return {
        "exists": True,
        "status": session["status"],
        "staff_assigned": session.get("staff_assigned"),
        "messages": chat_messages,
    }


# ── POST /tickets/{session_id}/accept ─────────────────────────────────
@router.post("/tickets/{session_id}/accept")
async def accept_ticket(session_id: str, body: dict = None):
    session = SESSIONS_DB.get(session_id)
    if not session:
        return {"error": "Session not found"}
    if session["status"] == "HUMAN_HANDLING":
        return {"error": f"Case đã được {session['staff_assigned']} tiếp nhận"}

    staff_name = (body or {}).get("staff_name", "Nhân viên CSKH")
    session["status"] = "HUMAN_HANDLING"
    session["staff_assigned"] = staff_name

    redis = _get_redis()
    try:
        await redis.publish(f"session_{session_id}", json.dumps({
            "type": "session:assigned",
            "assigned_to": staff_name,
        }))
    finally:
        await redis.aclose()
    return {"success": True}


# ── POST /tickets/{session_id}/close ──────────────────────────────────
@router.post("/tickets/{session_id}/close")
async def close_ticket(session_id: str):
    session = SESSIONS_DB.get(session_id)
    if not session:
        return {"error": "Session not found"}

    session["status"] = "RESOLVED"
    session["staff_assigned"] = None

    redis = _get_redis()
    try:
        await redis.publish(f"session_{session_id}", json.dumps({
            "type": "session:resolved",
            "assigned_to": None,
        }))
    finally:
        await redis.aclose()
    return {"success": True}


# ── POST /submit ──────────────────────────────────────────────────────
@router.post("/submit", response_model=SupportResponse)
async def submit_request(request: SupportRequest):
    """Tiếp nhận yêu cầu hỗ trợ, chạy qua pipeline LangGraph, trả kết quả."""
    timestamp = datetime.now().isoformat(timespec="seconds")
    customer_id = request.customer_id

    # Tạo session mới nếu chưa có
    if customer_id not in SESSIONS_DB:
        SESSIONS_DB[customer_id] = {
            "id": customer_id,
            "customer": customer_id,
            "status": "AI_HANDLING",
            "staff_assigned": None,
            "escalation_reason": "",
            "priority": "",
            "createdAt": datetime.now().strftime("%H:%M:%S"),
            "messages": [],
            "log": [],
            "type": "",
        }

    session = SESSIONS_DB[customer_id]

    # Nếu đang HUMAN_HANDLING, không chạy AI pipeline
    if session["status"] == "HUMAN_HANDLING":
        session["messages"].append({"sender_type": "customer", "content": request.message, "timestamp": timestamp})
        return SupportResponse(
            ticket_id=customer_id, status="HUMAN_HANDLING",
            response="Tin nhắn đã được gửi đến nhân viên hỗ trợ.",
            classification=session["type"], priority=session["priority"],
        )

    # Nếu đã RESOLVED, khách nhắn lại → mở session mới (AI_HANDLING)
    if session["status"] == "RESOLVED":
        session["status"] = "AI_HANDLING"
        session["staff_assigned"] = None
        session["log"] = []

    session["messages"].append({"sender_type": "customer", "content": request.message, "timestamp": timestamp})

    # Chạy LangGraph pipeline
    initial_state = {
        "customer_id": customer_id,
        "channel": request.channel,
        "message": request.message,
        "timestamp": timestamp,
        "metadata": request.metadata,
        "ticket_id": customer_id,
        "is_duplicate": False,
        "duplicate_ticket_id": "",
        "classification": "",
        "priority": "",
        "has_sufficient_info": True,
        "requires_human": False,
        "rag_documents": [],
        "similarity_score": 0.0,
        "embedding_vector": [],
        "response": "",
        "escalation_reason": "",
        "status": "processing",
        "processing_log": [],
    }

    result = workflow.invoke(initial_state)

    # Cập nhật session
    session["type"] = result.get("classification", "")
    session["priority"] = result.get("priority", "")
    session["log"].extend(result.get("processing_log", []))

    if result.get("status") == "escalated":
        session["status"] = "PENDING_ESCALATION"
        session["escalation_reason"] = result.get("escalation_reason", "")
    else:
        session["status"] = "RESOLVED"

    if result.get("response"):
        session["messages"].append({
            "sender_type": "ai",
            "content": result.get("response", ""),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        })

    return SupportResponse(
        ticket_id=customer_id,
        status=session["status"],
        response=result.get("response", ""),
        classification=result.get("classification", ""),
        priority=result.get("priority", ""),
        escalation_reason=result.get("escalation_reason", ""),
        is_duplicate=result.get("is_duplicate", False),
        duplicate_ticket_id=result.get("duplicate_ticket_id", ""),
        similarity_score=result.get("similarity_score", 0.0),
        rag_documents=result.get("rag_documents", []),
        processing_log=result.get("processing_log", []),
    )
