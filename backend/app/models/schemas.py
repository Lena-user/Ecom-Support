"""Pydantic models cho API request/response."""

from pydantic import BaseModel, Field


class SupportRequest(BaseModel):
    """Yêu cầu hỗ trợ từ khách hàng."""

    customer_id: str = Field(..., description="Mã khách hàng")
    channel: str = Field(
        ..., pattern="^(web_chat|email)$", description="Kênh gửi: web_chat hoặc email"
    )
    message: str = Field(..., min_length=1, description="Nội dung yêu cầu")
    metadata: dict = Field(default_factory=dict, description="Thông tin bổ sung")


class SupportResponse(BaseModel):
    """Kết quả xử lý trả về cho khách hàng / dashboard."""

    ticket_id: str
    status: str
    response: str
    classification: str
    priority: str
    escalation_reason: str = ""
    is_duplicate: bool = False
    duplicate_ticket_id: str = ""
    similarity_score: float = 0.0
    rag_documents: list[dict] = []
    processing_log: list[str] = []
