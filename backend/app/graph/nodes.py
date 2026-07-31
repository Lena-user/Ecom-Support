"""Graph nodes — mỗi hàm là 1 bước xử lý trong pipeline.

Bước 3: classify dùng Gemini Flash, rag_respond dùng Gemini để sinh câu trả lời.
Document retrieval vẫn dùng mock KB (bước 4 sẽ thay bằng Qdrant embedding).

Mỗi node nhận SupportState, trả về dict chỉ chứa các field cần cập nhật.
Field processing_log dùng Annotated[list, operator.add] nên trả về list
sẽ được append vào log hiện tại (không ghi đè).
"""

import time
import uuid
from datetime import datetime
from qdrant_client.models import Filter, FieldCondition, MatchValue, PointStruct, Range

from app import settings_store
from app.graph.state import SupportState
from app.llm import classify_message, generate_rag_response, get_embedding
from app.qdrant import get_qdrant

# ============================================================
# Mock knowledge base (thay bằng Qdrant RAG ở bước 3-4)
# ============================================================
MOCK_KB = [
    {
        "id": "kb_return",
        "keywords": ["đổi trả", "trả hàng", "đổi hàng", "hoàn trả", "trả lại"],
        "source": "Chính sách đổi trả",
        "content": (
            "Sản phẩm được đổi trả trong vòng 7 ngày kể từ ngày nhận hàng. "
            "Điều kiện: sản phẩm chưa qua sử dụng, còn nguyên tem/nhãn, "
            "có hóa đơn mua hàng. Phí vận chuyển đổi trả do người mua chịu, "
            "trừ trường hợp lỗi từ nhà bán hàng."
        ),
        "mock_similarity": 0.92,
    },
    {
        "id": "kb_shipping",
        "keywords": ["giao hàng", "vận chuyển", "ship", "thời gian giao", "bao lâu"],
        "source": "Chính sách vận chuyển",
        "content": (
            "Thời gian giao hàng: Nội thành HCM/HN: 1-2 ngày làm việc. "
            "Ngoại thành: 3-5 ngày làm việc. Đơn hàng trên 500.000đ được "
            "miễn phí vận chuyển. Theo dõi đơn hàng tại mục 'Đơn hàng của tôi'."
        ),
        "mock_similarity": 0.88,
    },
    {
        "id": "kb_voucher",
        "keywords": ["mã giảm giá", "voucher", "khuyến mãi", "coupon", "mã"],
        "source": "Hướng dẫn sử dụng mã giảm giá",
        "content": (
            "Nhập mã giảm giá tại bước thanh toán, ô 'Mã giảm giá'. "
            "Mỗi đơn hàng chỉ áp dụng 1 mã. Mã có thời hạn sử dụng "
            "và điều kiện đơn tối thiểu. Kiểm tra mục 'Ví voucher' "
            "để xem các mã đang có."
        ),
        "mock_similarity": 0.90,
    },
    {
        "id": "kb_payment_faq",
        "keywords": ["thanh toán bằng gì", "phương thức", "cách thanh toán", "trả tiền bằng"],
        "source": "FAQ Thanh toán",
        "content": (
            "Hỗ trợ thanh toán qua: COD (tiền mặt khi nhận hàng), "
            "chuyển khoản ngân hàng, ví MoMo, ZaloPay, thẻ Visa/Mastercard. "
            "Thanh toán online được giảm thêm 2%."
        ),
        "mock_similarity": 0.85,
    },
]

# Mock store cho duplicate check (trong production dùng Qdrant embedding)
_recent_messages: dict[str, list[dict]] = {}


# ============================================================
# NODE 1: Ingestion — chuẩn hóa input
# ============================================================
def ingest(state: SupportState) -> dict:
    """Chuẩn hóa input, tạo ticket ID."""
    ticket_id = f"TK-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "ticket_id": ticket_id,
        "processing_log": [
            f"[{now}] INGEST: Tạo ticket {ticket_id} | "
            f"kênh={state['channel']} | khách={state['customer_id']}"
        ],
    }


# ============================================================
# NODE 2: Duplicate Check — dùng Qdrant (Semantic Search)
# ============================================================
def check_duplicate(state: SupportState) -> dict:
    """Kiểm tra trùng lặp bằng Vector Search trên Qdrant, giới hạn trong
    khoảng thời gian duplicate_window_hours cấu hình được (Admin > Cấu hình AI)."""
    customer_id = state["customer_id"]
    message = state["message"].strip()
    now = datetime.now().isoformat(timespec="seconds")
    now_epoch = time.time()
    ai_settings = settings_store.get_settings()
    window_seconds = ai_settings["duplicate_window_hours"] * 3600
    qdrant = get_qdrant()
    vector = get_embedding(message)

    # Tìm kiếm ticket cũ của ĐÚNG khách hàng này, trong window_hours gần đây
    search_result = qdrant.search(
        collection_name="tickets",
        query_vector=vector,
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="customer_id",
                    match=MatchValue(value=customer_id)
                ),
                FieldCondition(
                    key="timestamp_epoch",
                    range=Range(gte=now_epoch - window_seconds),
                ),
            ]
        ),
        limit=1,
    )
    
    # Ngưỡng duplicate khá cao (0.95) để tránh bắt nhầm
    if search_result and search_result[0].score >= 0.95:
        prev_ticket = search_result[0].payload.get("ticket_id", "Unknown")
        return {
            "is_duplicate": True,
            "duplicate_ticket_id": prev_ticket,
            "response": (
                f"Mình thấy bạn vừa hỏi câu này trước đó rồi ở mã hỗ trợ "
                f"{prev_ticket}. Bạn xem lại câu trả lời ở trên nhé!"
            ),
            "status": "duplicate",
            "embedding_vector": vector,
            "processing_log": [
                f"[{now}] DUPLICATE_CHECK: Trùng lặp ngữ nghĩa với ticket "
                f"{prev_ticket} (score={search_result[0].score:.2f}) → dừng xử lý"
            ],
        }

    # Lưu message hiện tại vào store
    point_id = int(time.time() * 1000) % (2**63 - 1) # Generate a pseudo-random integer ID
    qdrant.upsert(
        collection_name="tickets",
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "message": message,
                    "ticket_id": state["ticket_id"],
                    "customer_id": customer_id,
                    "timestamp": state["timestamp"],
                    "timestamp_epoch": now_epoch,
                }
            )
        ]
    )

    return {
        "is_duplicate": False,
        "duplicate_ticket_id": "",
        "embedding_vector": vector,
        "processing_log": [
            f"[{now}] DUPLICATE_CHECK: Không trùng lặp"
        ],
    }


# ============================================================
# NODE 3: Classification — phân loại bằng Gemini Flash
# ============================================================
def classify(state: SupportState) -> dict:
    """Phân loại yêu cầu bằng Gemini Flash (JSON mode).

    Gọi LLM để phân loại vào 8 loại, xác định priority và
    kiểm tra đủ thông tin hay không. Có fallback nếu API lỗi.
    """
    now = datetime.now().isoformat(timespec="seconds")

    # Gọi Gemini Flash
    result = classify_message(
        message=state["message"],
        channel=state["channel"],
    )

    classification = result["classification"]
    priority = result["priority"]
    has_sufficient_info = result["has_sufficient_info"]
    requires_human = result["requires_human"]
    reasoning = result.get("reasoning", "")

    # Xác định escalation_reason dựa trên phân loại
    escalation_reasons = {
        "complaint": "Khiếu nại sản phẩm/dịch vụ — cần nhân viên xử lý",
        "payment": "Yêu cầu liên quan thanh toán/hoàn tiền — cần xác minh",
        "emergency": "Yêu cầu khẩn cấp — cần xử lý ngay",
        "human_requested": "Khách hàng yêu cầu nói chuyện với nhân viên",
    }
    escalation_reason = escalation_reasons.get(classification, "")

    # Từ khoá escalate thủ công (Admin > Cấu hình AI) — ép escalate dù Gemini
    # phân loại là gì, ví dụ khách đề cập tới pháp lý/báo chí.
    ai_settings = settings_store.get_settings()
    message_lower = state["message"].lower()
    matched_keyword = next(
        (kw for kw in ai_settings["escalate_keywords"] if kw.strip() and kw.strip().lower() in message_lower),
        None,
    )
    if matched_keyword:
        requires_human = True
        if not escalation_reason:
            escalation_reason = f"Phát hiện từ khoá nhạy cảm cấu hình sẵn: '{matched_keyword}'"

    # Xác định route tiếp theo cho log
    if classification == "spam":
        next_step = "→ lọc bỏ"
    elif not has_sufficient_info or classification == "missing_info":
        next_step = "→ hỏi lại"
    elif classification in escalation_reasons or requires_human:
        next_step = "→ ESCALATE"
    else:
        next_step = "→ RAG"

    return {
        "classification": classification,
        "priority": priority,
        "has_sufficient_info": has_sufficient_info,
        "requires_human": requires_human,
        "escalation_reason": escalation_reason,
        "processing_log": [
            f"[{now}] CLASSIFY [Gemini]: {classification}, "
            f"priority={priority} {next_step} | LLM reasoning: {reasoning}"
        ],
    }


# ============================================================
# NODE 4a: Handle Spam — log và dừng
# ============================================================
def handle_spam(state: SupportState) -> dict:
    """Log spam và dừng xử lý."""
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "response": "Tin nhắn đã được ghi nhận. Cảm ơn bạn.",
        "status": "spam",
        "processing_log": [
            f"[{now}] SPAM_FILTER: Đã lọc và log tin nhắn spam"
        ],
    }


# ============================================================
# NODE 4b: Ask Info — hỏi lại thông tin thiếu
# ============================================================
def ask_info(state: SupportState) -> dict:
    """Yêu cầu khách cung cấp thêm thông tin."""
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "response": (
            "Để hỗ trợ bạn tốt hơn, vui lòng cung cấp thêm thông tin:\n"
            "- Mã đơn hàng (nếu liên quan đến đơn hàng)\n"
            "- Mô tả chi tiết vấn đề bạn gặp phải\n"
            "Cảm ơn bạn!"
        ),
        "status": "awaiting_info",
        "processing_log": [
            f"[{now}] ASK_INFO: Đã gửi yêu cầu bổ sung thông tin cho khách"
        ],
    }


# ============================================================
# NODE 5: RAG Respond — tìm tài liệu + Gemini sinh câu trả lời
# ============================================================
def rag_respond(state: SupportState) -> dict:
    """Tìm tài liệu liên quan bằng Qdrant và dùng Gemini sinh câu trả lời.

    - Retrieval: Qdrant Vector Search (top-3, lọc rác bằng similarity_threshold)
    - Response generation + đánh giá độ tin cậy: Gemini (has_sufficient_grounding)
      — quyết định resolved/escalate dựa vào chính đánh giá của Gemini, không
      dựa vào con số similarity nữa (con số chỉ dùng để lọc bớt tài liệu rác
      trước khi đưa cho Gemini đọc).
    """
    message = state["message"].strip()
    now = datetime.now().isoformat(timespec="seconds")

    qdrant = get_qdrant()
    vector = state.get("embedding_vector")
    if not vector:
        vector = get_embedding(message)

    similarity_threshold = settings_store.get_settings()["similarity_threshold"]

    # Lấy top-3 tài liệu gần nghĩa nhất, lọc bớt tài liệu hoàn toàn không liên quan
    search_result = qdrant.search(
        collection_name="knowledge_base",
        query_vector=vector,
        limit=3,
        score_threshold=similarity_threshold,
    )

    rag_documents = [
        {
            "id": r.payload["id"],
            "source": r.payload["source"],
            "content": r.payload["content"],
            "score": r.score,
        }
        for r in search_result
    ]
    best_score = rag_documents[0]["score"] if rag_documents else 0.0

    # Gemini tự đọc tài liệu + câu hỏi, sinh câu trả lời và tự đánh giá độ tin cậy
    result = generate_rag_response(
        message=state["message"],
        documents=rag_documents,
    )
    has_sufficient_grounding = result["has_sufficient_grounding"]
    reasoning = result.get("reasoning", "")

    escalation_reason = (
        "" if has_sufficient_grounding
        else f"AI đánh giá chưa đủ căn cứ tài liệu để trả lời: {reasoning}"
    )
    gate_result = "Đủ căn cứ trả lời" if has_sufficient_grounding else "Không đủ căn cứ → chuyển nhân viên"

    return {
        "rag_documents": rag_documents,
        "similarity_score": best_score,
        "response": result["answer"],
        "escalation_reason": escalation_reason,
        "rag_has_sufficient_grounding": has_sufficient_grounding,
        "needs_kb_review": not has_sufficient_grounding,
        "processing_log": [
            f"[{now}] RAG [Gemini]: {len(rag_documents)} tài liệu (best={best_score:.2f}) "
            f"→ {gate_result} | {reasoning}"
        ],
    }


# ============================================================
# NODE 6: Escalate — đóng gói bối cảnh cho nhân sự
# ============================================================
def escalate(state: SupportState) -> dict:
    """Đóng gói bối cảnh và chuyển cho nhân sự phụ trách."""
    now = datetime.now().isoformat(timespec="seconds")
    reason = state.get("escalation_reason", "Không xác định")
    classification = state.get("classification", "unknown")
    priority = state.get("priority", "medium")

    response = (
        f"Yêu cầu của bạn đã được chuyển cho nhân viên hỗ trợ.\n"
        f"Mã ticket: {state['ticket_id']}\n"
        f"Thời gian phản hồi dự kiến: "
        f"{'15 phút' if priority == 'critical' else '1-2 giờ làm việc'}.\n"
        f"Cảm ơn bạn đã kiên nhẫn!"
    )

    return {
        "response": response,
        "status": "escalated",
        "processing_log": [
            f"[{now}] ESCALATE: Chuyển nhân viên | "
            f"loại={classification} | ưu tiên={priority} | "
            f"lý do: {reason}"
        ],
    }


# ============================================================
# NODE 7: Respond — hoàn tất phản hồi tự động
# ============================================================
def respond(state: SupportState) -> dict:
    """Hoàn tất phản hồi — set status resolved."""
    now = datetime.now().isoformat(timespec="seconds")

    # Nếu duplicate, response đã được set ở check_duplicate
    if state.get("is_duplicate"):
        return {
            "processing_log": [
                f"[{now}] RESPOND: Trả lời tham chiếu ticket cũ "
                f"{state.get('duplicate_ticket_id', '')}"
            ],
        }

    return {
        "status": "resolved",
        "processing_log": [
            f"[{now}] RESPOND: Trả lời tự động thành công"
        ],
    }


# ============================================================
# Conditional edge functions — quyết định node tiếp theo
# ============================================================
def after_duplicate_check(state: SupportState) -> str:
    """Sau bước duplicate check: trùng → respond, không trùng → classify."""
    return "respond" if state.get("is_duplicate") else "classify"


def after_classify(state: SupportState) -> str:
    """Sau bước classify: route dựa trên loại yêu cầu.

    Đây là node routing chính — map phân loại → hành động tiếp theo.
    """
    classification = state.get("classification", "")
    requires_human = state.get("requires_human", False)
    has_sufficient_info = state.get("has_sufficient_info", True)

    if classification == "spam":
        return "handle_spam"

    if not has_sufficient_info or classification == "missing_info":
        return "ask_info"

    # Các loại cần escalate: khiếu nại, thanh toán, khẩn cấp, khách yêu cầu người
    if classification in ("complaint", "payment", "emergency", "human_requested"):
        return "escalate"
    if requires_human:
        return "escalate"

    # Còn lại (info_inquiry, technical) → thử RAG
    return "rag_respond"


def after_rag(state: SupportState) -> str:
    """Sau bước RAG: chỉ tự trả lời nếu Gemini đánh giá đủ căn cứ tài liệu,
    ngược lại chuyển cho nhân viên (an toàn khi không chắc chắn)."""
    return "respond" if state.get("rag_has_sufficient_grounding", True) else "escalate"
