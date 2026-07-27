"""API routes — endpoint tiếp nhận yêu cầu hỗ trợ."""

from datetime import datetime

from fastapi import APIRouter

from typing import List, Dict, Any
from app.graph.workflow import workflow
from app.models.schemas import SupportRequest, SupportResponse

router = APIRouter(prefix="/api/support", tags=["support"])

# Simple In-Memory Database for Demo Purposes
TICKETS_DB: List[Dict[str, Any]] = []

@router.get("/tickets")
async def get_tickets():
    """Lấy danh sách tickets để hiển thị trên Staff Dashboard"""
    return TICKETS_DB[::-1]

@router.post("/submit", response_model=SupportResponse)
async def submit_request(request: SupportRequest):
    """Tiếp nhận yêu cầu hỗ trợ, chạy qua pipeline LangGraph, trả kết quả.

    Pipeline gồm: ingest → duplicate check → classify → route →
    (RAG respond / escalate / ask info / spam filter) → respond.
    """
    timestamp = datetime.now().isoformat(timespec="seconds")
    
    # Khởi tạo state ban đầu cho graph
    initial_state = {
        # Input từ request
        "customer_id": request.customer_id,
        "channel": request.channel,
        "message": request.message,
        "timestamp": timestamp,
        "metadata": request.metadata,
        # Các field sẽ được điền bởi các node
        "ticket_id": "",
        "is_duplicate": False,
        "duplicate_ticket_id": "",
        "classification": "",
        "priority": "",
        "has_sufficient_info": True,
        "requires_human": False,
        "rag_documents": [],
        "similarity_score": 0.0,
        "response": "",
        "escalation_reason": "",
        "status": "processing",
        "processing_log": [],
    }

    # Chạy graph
    result = workflow.invoke(initial_state)

    response = SupportResponse(
        ticket_id=result["ticket_id"],
        status=result["status"],
        response=result["response"],
        classification=result["classification"],
        priority=result["priority"],
        escalation_reason=result.get("escalation_reason", ""),
        is_duplicate=result.get("is_duplicate", False),
        duplicate_ticket_id=result.get("duplicate_ticket_id", ""),
        similarity_score=result.get("similarity_score", 0.0),
        rag_documents=result.get("rag_documents", []),
        processing_log=result.get("processing_log", []),
    )
    
    # Save to DB for the Dashboard
    TICKETS_DB.append({
        "id": result["ticket_id"],
        "status": result["status"],
        "priority": result["priority"],
        "type": result["classification"],
        "customer": request.customer_id,
        "createdAt": datetime.now().strftime("%H:%M:%S"),
        "log": result.get("processing_log", []),
        "similarityScore": result.get("similarity_score", 0.0),
        "message": request.message
    })

    return response
