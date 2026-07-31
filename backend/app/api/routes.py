"""API routes — endpoint tiếp nhận yêu cầu hỗ trợ."""

import json
import re
import uuid
from datetime import datetime
from typing import Dict, Any, Literal
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import knowledge_gaps, session_store, settings_store, staff_store, uploads
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


_INGEST_RE = re.compile(r"^\[(?P<ts>[^\]]+)\] INGEST:")
_CLASSIFY_RE = re.compile(r"CLASSIFY \[Gemini\]: (?P<classification>\w+),")
_DUPLICATE_RE = re.compile(r"DUPLICATE_CHECK: Trùng lặp")


def _split_into_requests(log: list) -> list:
    """Tách `processing_log` của 1 session thành từng lượt request riêng biệt.

    Mỗi lượt khách gửi tin nhắn trong khi AI đang xử lý (status AI_HANDLING) sẽ
    chạy lại toàn bộ pipeline, luôn bắt đầu bằng đúng 1 dòng "INGEST:" — dùng
    mốc này để đếm chính xác số request thay vì đếm theo session (1 session có
    thể chứa nhiều request nếu khách hỏi nhiều câu khác nhau trong cùng phiên)."""
    requests_: list = []
    current: Dict[str, Any] | None = None
    for line in log:
        m = _INGEST_RE.match(line)
        if m:
            if current is not None:
                requests_.append(current)
            current = {"timestamp": m.group("ts"), "classification": None}
            continue
        if current is None:
            continue
        cm = _CLASSIFY_RE.search(line)
        if cm:
            current["classification"] = cm.group("classification")
        elif _DUPLICATE_RE.search(line):
            current["classification"] = "duplicate"
    if current is not None:
        requests_.append(current)
    return requests_


def _serialize_chat_messages(messages: list) -> list:
    """Chuyển messages thô của session → format Frontend hiểu (role/sender/
    attachment_url) — dùng chung cho GET /session (khách hàng) và GET /tickets
    (nhân viên), để nhân viên luôn thấy TOÀN BỘ lịch sử hội thoại (bối cảnh đầy
    đủ) thay vì chỉ 1 tin nhắn được chọn tuỳ tiện (mới nhất hoặc đầu tiên)."""
    result = []
    for m in messages:
        sender_type = m.get("sender_type", "")
        role = "user" if sender_type == "customer" else "bot"
        result.append({
            "role": role,
            "content": m.get("content", ""),
            "sender": sender_type if sender_type in ("ai", "staff") else None,
            "attachment_url": m.get("attachment_url"),
        })
    return result


def _serialize_session(s: Dict[str, Any]) -> Dict[str, Any]:
    """Chuyển session dict → format mà Frontend Ticket interface chờ đợi.

    "message"/"attachment_url" = tin nhắn MỚI NHẤT của khách (chỉ dùng cho
    preview rút gọn trong danh sách ticket, kiểu "tin nhắn cuối" của app chat).
    "messages" = TOÀN BỘ lịch sử hội thoại — dùng khi mở chi tiết ticket, để
    nhân viên thấy đủ bối cảnh (kể cả ảnh đính kèm ở bất kỳ tin nhắn nào).
    """
    latest_msg = ""
    attachment_url = None
    for m in reversed(s.get("messages", [])):
        if m.get("sender_type") == "customer":
            latest_msg = m.get("content", "")
            attachment_url = m.get("attachment_url")
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
        "attachment_url": attachment_url,
        "messages": _serialize_chat_messages(s.get("messages", [])),
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
    """Thống kê tổng hợp từ session store cho trang Admin (dữ liệu thật, không mock).

    Có 2 đơn vị đếm khác nhau, không dùng lẫn lộn:
    - "request": mỗi lượt khách gửi tin nhắn được AI pipeline xử lý (1 session có
      thể có nhiều request nếu khách hỏi nhiều câu trong cùng phiên) — dùng cho
      total_requests, by_classification, requests_by_hour.
    - "case"/"session": 1 ticket của 1 khách hàng — dùng cho auto_resolved_rate,
      escalated_count, by_type_status. Phân loại "tự xử lý" vs "chuyển người"
      dựa vào cờ was_escalated (đã TỪNG chuyển người hay chưa), KHÔNG dựa vào
      status hiện tại — vì 1 ticket đã escalate rồi được nhân viên đóng ca cũng
      có status RESOLVED giống hệt ticket AI tự xử lý xong, nếu chỉ nhìn status
      cuối sẽ đếm nhầm ca "chuyển người" thành "AI tự xử lý".
    """
    sessions = await session_store.list_all()
    total_sessions = len(sessions)

    all_requests: list[Dict[str, Any]] = []
    for s in sessions:
        all_requests.extend(_split_into_requests(s.get("log", [])))
    total_requests = len(all_requests)

    by_classification: Dict[str, int] = {}
    by_hour: Dict[str, int] = {}
    for r in all_requests:
        classification = r["classification"] or "unknown"
        by_classification[classification] = by_classification.get(classification, 0) + 1

        try:
            hour_label = datetime.fromisoformat(r["timestamp"]).strftime("%d/%m %Hh")
        except ValueError:
            hour_label = "??"
        by_hour[hour_label] = by_hour.get(hour_label, 0) + 1

    by_type_status: Dict[str, Dict[str, int]] = {}
    resolved_without_escalation = 0
    escalated_count = 0
    for s in sessions:
        classification = s.get("type") or "unknown"
        bucket = by_type_status.setdefault(classification, {"auto": 0, "escalate": 0})
        if s.get("was_escalated"):
            bucket["escalate"] += 1
            escalated_count += 1
        elif s["status"] == "RESOLVED":
            bucket["auto"] += 1
            resolved_without_escalation += 1

    auto_resolved_rate = (
        round((resolved_without_escalation / total_sessions) * 100, 1) if total_sessions else 0.0
    )

    recent_logs: list[str] = []
    for s in sessions:
        recent_logs.extend(s.get("log", []))
    recent_logs = recent_logs[-30:]

    csat_positive = sum(1 for s in sessions if s.get("csat_rating") == "up")
    csat_negative = sum(1 for s in sessions if s.get("csat_rating") == "down")

    return {
        "total_requests": total_requests,
        "auto_resolved_rate": auto_resolved_rate,
        "escalated_count": escalated_count,
        "by_classification": by_classification,
        "by_type_status": by_type_status,
        "requests_by_hour": sorted(by_hour.items()),
        "recent_logs": recent_logs,
        "csat_positive": csat_positive,
        "csat_negative": csat_negative,
        "csat_total": csat_positive + csat_negative,
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

    return {
        "exists": True,
        "status": session["status"],
        "staff_assigned": session.get("staff_assigned"),
        "messages": _serialize_chat_messages(session.get("messages", [])),
    }


# ── POST /tickets/{customer_id}/rate ────────────────────────────────────
class CSATRatingIn(BaseModel):
    rating: Literal["up", "down"]


@router.post("/tickets/{customer_id}/rate")
async def rate_ticket(customer_id: str, payload: CSATRatingIn):
    """Khách hàng đánh giá câu trả lời (👍/👎) — công khai, không cần đăng nhập."""
    session = await session_store.get(customer_id)
    if not session:
        return {"error": "Session not found"}
    session["csat_rating"] = payload.rating
    await session_store.save(customer_id, session)
    return {"success": True}


# ── POST /tickets/{session_id}/accept ─────────────────────────────────
@router.post("/tickets/{session_id}/accept", dependencies=[_require_staff])
async def accept_ticket(session_id: str, body: dict = None):
    staff_name = (body or {}).get("staff_name", "Nhân viên CSKH")

    # try_accept() dùng Redis WATCH/MULTI/EXEC để đảm bảo chỉ 1 trong nhiều
    # request "Tiếp nhận" gần như đồng thời được thành công — tránh trường hợp
    # 2 nhân viên cùng bấm tiếp nhận 1 ca mà cả 2 đều nhận phản hồi "thành
    # công" (đọc-rồi-ghi thường sẽ khiến người ghi sau âm thầm đè người trước).
    result, session = await session_store.try_accept(session_id, staff_name)

    if result == "not_found":
        return {"error": "Session not found"}
    if result == "already_handling":
        return {"error": f"Case đã được {session['staff_assigned']} tiếp nhận"}
    if result == "not_pending":
        return {"error": "Ticket này hiện không ở trạng thái chờ tiếp nhận"}

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

    # Giữ nguyên staff_assigned (KHÔNG xoá về None) — cần biết ai đã xử lý ca
    # này để tính đúng "Tickets xử lý" ở Quản lý nhân sự và tab "Đã xong" ở
    # Dashboard (lọc theo staff_assigned === tên nhân viên đang đăng nhập).
    # Lần "Tiếp nhận" kế tiếp (nếu khách escalate lại) sẽ tự ghi đè giá trị này.
    session["status"] = "RESOLVED"
    await session_store.save(session_id, session)

    redis = _get_redis()
    try:
        await redis.publish(f"session_{session_id}", json.dumps({
            "type": "session:resolved",
            "assigned_to": session.get("staff_assigned"),
        }))
    finally:
        await redis.aclose()
    return {"success": True}


# ── POST /upload ──────────────────────────────────────────────────────
@router.post("/upload")
async def upload_attachment(file: UploadFile):
    """Nhận ảnh đính kèm từ khách hàng (công khai, không cần đăng nhập)."""
    content = await file.read()
    try:
        url = uploads.save_upload(content, file.content_type or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"url": url}


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
            "createdAt": timestamp,
            "messages": [],
            "log": [],
            "type": "",
            "csat_rating": None,
            "was_escalated": False,
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

    # Nếu đã RESOLVED, khách nhắn lại → mở lại AI_HANDLING trong cùng session.
    # Giữ nguyên "log" (không xoá) — cùng 1 cuộc hội thoại, giống cách "messages"
    # cũng không bị xoá; nếu không, mỗi vòng resolved→reopen sẽ xoá mất log các
    # request trước đó, khiến /stats đếm thiếu số request thật đã xử lý.
    if session["status"] == "RESOLVED":
        session["status"] = "AI_HANDLING"
        session["staff_assigned"] = None
        session["csat_rating"] = None

    session["messages"].append({
        "sender_type": "customer",
        "content": request.message,
        "timestamp": timestamp,
        "attachment_url": request.attachment_url,
    })

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
        # Cờ bền vững, không reset khi ticket được đóng sau đó — dùng để phân
        # biệt "AI tự xử lý hoàn toàn" với "đã từng chuyển người, dù cuối cùng
        # cũng ở status RESOLVED sau khi nhân viên đóng ca" (2 case rất khác
        # nhau nhưng nếu chỉ nhìn status cuối thì không phân biệt được).
        session["was_escalated"] = True
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


# ── Quản lý nhân sự (staff/admin accounts) ────────────────────────────────
class StaffIn(BaseModel):
    email: str
    name: str
    password: str = Field(..., min_length=3)
    role: Literal["staff", "admin"]


@router.get("/staff", dependencies=[_require_admin])
async def list_staff():
    """Danh sách tài khoản nhân viên/admin (không trả password_hash), kèm số
    ticket đã xử lý (tính từ session_store, khớp theo tên hiển thị).

    Đếm theo lịch sử "handled_by" (mỗi lần tiếp nhận đều được ghi thêm vào),
    KHÔNG đếm theo "staff_assigned" hiện tại — vì field đó chỉ giữ được 1 tên
    tại 1 thời điểm và bị ghi đè mỗi khi khách escalate lại, nên đếm theo nó
    sẽ làm mất công của các vòng tiếp nhận trước đó."""
    accounts = await staff_store.list_all()
    sessions = await session_store.list_all()
    ticket_counts: Dict[str, int] = {}
    for s in sessions:
        for name in s.get("handled_by", []):
            ticket_counts[name] = ticket_counts.get(name, 0) + 1

    return [
        {
            "email": a["email"],
            "name": a["name"],
            "role": a["role"],
            "ticket_count": ticket_counts.get(a["name"], 0),
        }
        for a in accounts
    ]


@router.post("/staff", dependencies=[_require_admin])
async def create_staff(payload: StaffIn):
    try:
        record = await staff_store.create(
            email=payload.email, name=payload.name, role=payload.role, password=payload.password
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"email": record["email"], "name": record["name"], "role": record["role"]}


@router.delete("/staff/{email}")
async def delete_staff(email: str, requester: dict = Depends(require_role("admin"))):
    if email == requester.get("sub"):
        raise HTTPException(status_code=400, detail="Không thể tự xoá tài khoản đang đăng nhập")

    accounts = await staff_store.list_all()
    target = next((a for a in accounts if a["email"] == email), None)
    if not target:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")

    admins = [a for a in accounts if a["role"] == "admin"]
    if target["role"] == "admin" and len(admins) <= 1:
        raise HTTPException(status_code=400, detail="Không thể xoá admin cuối cùng")

    await staff_store.delete(email)
    return {"success": True}
