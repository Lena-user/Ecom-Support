"""API routes — endpoint tiếp nhận yêu cầu hỗ trợ."""

import json
import uuid
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app import knowledge_gaps, session_store, settings_store
from app.auth import require_role
from app.graph.workflow import workflow
from app.llm import get_embedding
from app.models.schemas import SupportRequest, SupportResponse
from app.qdrant import get_qdrant

router = APIRouter(prefix="/api/support", tags=["support"])

KB_COLLECTION = "knowledge_base"

# Yêu cầu đăng nhập cho các endpoint quản trị (không áp cho /submit, /session — khách hàng ẩn danh vẫn chat được)
_require_staff = Depends(require_role("staff", "admin"))
_require_admin = Depends(require_role("admin"))


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
@router.get("/tickets", dependencies=[_require_staff])
async def get_tickets():
    """Trả danh sách sessions cho Staff Dashboard (mới nhất lên đầu)."""
    sessions = await session_store.list_all()
    items = [_serialize_session(s) for s in sessions]
    items.sort(key=lambda x: x["createdAt"], reverse=True)
    return items


# ── GET /stats ────────────────────────────────────────────────────────
@router.get("/stats", dependencies=[_require_admin])
async def get_stats():
    """Thống kê tổng hợp từ session store cho trang Admin (dữ liệu thật, không mock)."""
    sessions = await session_store.list_all()
    total = len(sessions)

    by_classification: Dict[str, int] = {}
    by_type_status: Dict[str, Dict[str, int]] = {}
    by_hour: Dict[str, int] = {}
    resolved_without_escalation = 0

    for s in sessions:
        classification = s.get("type") or "unknown"
        by_classification[classification] = by_classification.get(classification, 0) + 1

        bucket = by_type_status.setdefault(classification, {"auto": 0, "escalate": 0})
        if s["status"] in ("PENDING_ESCALATION", "HUMAN_HANDLING"):
            bucket["escalate"] += 1
        elif s["status"] == "RESOLVED":
            bucket["auto"] += 1
            resolved_without_escalation += 1

        created_at = s.get("createdAt", "")
        hour = created_at.split(":")[0] if ":" in created_at else "??"
        hour_label = f"{hour}:00"
        by_hour[hour_label] = by_hour.get(hour_label, 0) + 1

    auto_resolved_rate = round((resolved_without_escalation / total) * 100, 1) if total else 0.0

    recent_logs: list[str] = []
    for s in sessions:
        recent_logs.extend(s.get("log", []))
    recent_logs = recent_logs[-30:]

    return {
        "total_requests": total,
        "auto_resolved_rate": auto_resolved_rate,
        "escalated_count": sum(
            1 for s in sessions if s["status"] in ("PENDING_ESCALATION", "HUMAN_HANDLING")
        ),
        "by_classification": by_classification,
        "by_type_status": by_type_status,
        "requests_by_hour": sorted(by_hour.items()),
        "recent_logs": recent_logs,
    }


# ── GET /session/{customer_id} ────────────────────────────────────────
@router.get("/session/{customer_id}")
async def get_session(customer_id: str):
    """Khôi phục session cho khách hàng khi quay lại trang chat.

    Trả về trạng thái session + toàn bộ lịch sử tin nhắn.
    """
    session = await session_store.get(customer_id)
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
@router.post("/tickets/{session_id}/accept", dependencies=[_require_staff])
async def accept_ticket(session_id: str, body: dict = None):
    session = await session_store.get(session_id)
    if not session:
        return {"error": "Session not found"}
    if session["status"] == "HUMAN_HANDLING":
        return {"error": f"Case đã được {session['staff_assigned']} tiếp nhận"}

    staff_name = (body or {}).get("staff_name", "Nhân viên CSKH")
    session["status"] = "HUMAN_HANDLING"
    session["staff_assigned"] = staff_name
    await session_store.save(session_id, session)

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
@router.post("/tickets/{session_id}/close", dependencies=[_require_staff])
async def close_ticket(session_id: str):
    session = await session_store.get(session_id)
    if not session:
        return {"error": "Session not found"}

    session["status"] = "RESOLVED"
    session["staff_assigned"] = None
    await session_store.save(session_id, session)

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

    session = await session_store.get(customer_id)
    if session is None:
        session = {
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

    # Nếu đang HUMAN_HANDLING, không chạy AI pipeline
    if session["status"] == "HUMAN_HANDLING":
        session["messages"].append({"sender_type": "customer", "content": request.message, "timestamp": timestamp})
        await session_store.save(customer_id, session)
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
        "rag_has_sufficient_grounding": True,
        "needs_kb_review": False,
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

    if result.get("needs_kb_review"):
        await knowledge_gaps.log_gap(
            message=request.message,
            reasoning=result.get("escalation_reason", ""),
            ticket_id=customer_id,
            classification=result.get("classification", ""),
        )

    if result.get("response"):
        session["messages"].append({
            "sender_type": "ai",
            "content": result.get("response", ""),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        })

    await session_store.save(customer_id, session)

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


# ── GET / PUT /settings ─────────────────────────────────────────────────
@router.get("/settings", dependencies=[_require_admin])
async def get_ai_settings():
    """Cấu hình AI hiện tại (similarity threshold, duplicate window, escalate keywords)."""
    return settings_store.get_settings()


class AISettingsIn(BaseModel):
    similarity_threshold: float = Field(..., ge=0.0, le=1.0)
    duplicate_window_hours: int = Field(..., ge=1)
    escalate_keywords: list[str] = Field(default_factory=list)


@router.put("/settings", dependencies=[_require_admin])
async def update_ai_settings(payload: AISettingsIn):
    return settings_store.save_settings(payload.model_dump())


# ── GET /knowledge-gaps ──────────────────────────────────────────────────
@router.get("/knowledge-gaps", dependencies=[_require_admin])
async def get_knowledge_gaps():
    """Câu hỏi mà AI đánh giá không đủ căn cứ tài liệu để trả lời — dùng để
    admin xem và chủ động bổ sung Knowledge Base."""
    return await knowledge_gaps.list_gaps()


# ── Knowledge Base CRUD ──────────────────────────────────────────────────
class KBDocIn(BaseModel):
    source: str
    content: str


def _embed_kb_doc(doc: KBDocIn) -> list[float]:
    return get_embedding(f"{doc.source}: {doc.content}")


def _normalize_point_id(doc_id: str) -> int | str:
    """Qdrant point id chỉ chấp nhận unsigned int hoặc UUID string. Các tài liệu
    seed sẵn từ init_db.py dùng id số nguyên (vd "1"), tài liệu tạo qua UI dùng UUID."""
    return int(doc_id) if doc_id.isdigit() else doc_id


@router.get("/kb", dependencies=[_require_admin])
async def list_kb_docs():
    qdrant = get_qdrant()
    points, _ = qdrant.scroll(collection_name=KB_COLLECTION, limit=200, with_payload=True, with_vectors=False)
    return [
        {"id": p.id, "source": p.payload.get("source", ""), "content": p.payload.get("content", "")}
        for p in points
    ]


@router.post("/kb", dependencies=[_require_admin])
async def create_kb_doc(doc: KBDocIn):
    from qdrant_client.models import PointStruct

    qdrant = get_qdrant()
    doc_id = str(uuid.uuid4())
    vector = _embed_kb_doc(doc)
    qdrant.upsert(
        collection_name=KB_COLLECTION,
        points=[PointStruct(id=doc_id, vector=vector, payload={"id": doc_id, "source": doc.source, "content": doc.content})],
    )
    return {"id": doc_id, "source": doc.source, "content": doc.content}


@router.put("/kb/{doc_id}", dependencies=[_require_admin])
async def update_kb_doc(doc_id: str, doc: KBDocIn):
    from qdrant_client.models import PointStruct

    qdrant = get_qdrant()
    point_id = _normalize_point_id(doc_id)
    vector = _embed_kb_doc(doc)
    qdrant.upsert(
        collection_name=KB_COLLECTION,
        points=[PointStruct(id=point_id, vector=vector, payload={"id": doc_id, "source": doc.source, "content": doc.content})],
    )
    return {"id": doc_id, "source": doc.source, "content": doc.content}


@router.delete("/kb/{doc_id}", dependencies=[_require_admin])
async def delete_kb_doc(doc_id: str):
    qdrant = get_qdrant()
    qdrant.delete(collection_name=KB_COLLECTION, points_selector=[_normalize_point_id(doc_id)])
    return {"success": True}
