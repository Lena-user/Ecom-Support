"""LangGraph state — định nghĩa dữ liệu chạy xuyên suốt luồng xử lý.

Dùng Annotated[list, operator.add] cho processing_log để mỗi node
append thêm log thay vì ghi đè — quan trọng cho observability.
"""

import operator
from typing import Annotated, TypedDict


class SupportState(TypedDict):
    """State chứa toàn bộ thông tin 1 request đi qua pipeline."""

    # --- Input (set bởi API, truyền vào graph) ---
    customer_id: str
    channel: str          # "web_chat" | "email"
    message: str
    timestamp: str
    metadata: dict

    # --- Ticket (set bởi ingest) ---
    ticket_id: str

    # --- Duplicate Check ---
    is_duplicate: bool
    duplicate_ticket_id: str

    # --- Classification ---
    classification: str       # 8 loại theo đề bài
    priority: str             # low | medium | high | critical
    has_sufficient_info: bool
    requires_human: bool      # khách chủ động yêu cầu gặp người

    # --- RAG ---
    rag_documents: list[dict]
    similarity_score: float
    embedding_vector: list[float]

    # --- Output ---
    response: str
    escalation_reason: str
    status: str  # processing | resolved | escalated | spam | awaiting_info | duplicate

    # --- Observability (append-only, mỗi node thêm log) ---
    processing_log: Annotated[list[str], operator.add]
