"""Gemini LLM client — wrapper cho Google GenAI SDK.

Cung cấp 2 hàm chính:
- classify_message(): Phân loại yêu cầu (dùng model nhanh)
- generate_rag_response(): Sinh câu trả lời từ tài liệu (dùng model chất lượng)
"""

import json
import logging

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

# Singleton client
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Lazy init Gemini client."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


# ============================================================
# Classification prompt
# ============================================================
CLASSIFY_PROMPT = """Bạn là hệ thống phân loại yêu cầu khách hàng cho sàn thương mại điện tử.

Phân loại tin nhắn sau vào ĐÚNG 1 trong các loại:
- "info_inquiry": Hỏi đáp thông tin (hỏi về chính sách đổi trả, thời gian giao hàng, cách dùng mã giảm giá, hướng dẫn chung)
- "complaint": Khiếu nại (báo cáo hàng lỗi, giao sai, giao chậm, không đúng mô tả - cần giải quyết cho 1 đơn hàng cụ thể)
- "technical": Yêu cầu kỹ thuật (lỗi app, không đăng nhập được, lỗi thanh toán kỹ thuật)
- "payment": Yêu cầu thanh toán nhạy cảm (hoàn tiền, tranh chấp giao dịch, mất tiền)
- "emergency": Khẩn cấp (gian lận, tài khoản bị hack, lừa đảo)
- "spam": Tin rác, quảng cáo, nội dung không liên quan
- "missing_info": Thiếu thông tin để xử lý (tin nhắn mơ hồ, không rõ yêu cầu)
- "human_requested": Khách hàng chủ động yêu cầu gặp nhân viên / người thật

LƯU Ý QUAN TRỌNG: 
- Nếu khách hàng HỎI VỀ CÁCH THỨC/CHÍNH SÁCH (VD: "Làm sao để đổi trả", "Trả hàng được không", "Sản phẩm lỗi đổi thế nào"), hãy xếp vào "info_inquiry" vì đây là câu hỏi chung.
- Chỉ xếp vào "complaint" khi khách ĐANG báo cáo một vấn đề cụ thể của họ (VD: "Hàng của tôi bị rách rồi", "Tôi nhận sai hàng").

Xác định mức ưu tiên:
- "low": Hỏi đáp thông tin chung
- "medium": Kỹ thuật, thiếu thông tin
- "high": Khiếu nại, thanh toán
- "critical": Khẩn cấp (gian lận, hack)

Trả về JSON với format:
{{
    "classification": "<loại>",
    "priority": "<mức ưu tiên>",
    "has_sufficient_info": true/false,
    "requires_human": true/false, // CHỈ true nếu là complaint, payment, emergency, human_requested hoặc vấn đề không thể tự động trả lời bằng FAQ
    "reasoning": "<giải thích ngắn gọn>"
}}

Tin nhắn khách hàng (kênh: {channel}):
\"\"\"{message}\"\"\"
"""


def classify_message(message: str, channel: str) -> dict:
    """Gọi Gemini Flash để phân loại yêu cầu khách hàng.

    Returns:
        Dict chứa classification, priority, has_sufficient_info, requires_human.
        Nếu API lỗi, fallback về phân loại mặc định.
    """
    try:
        client = _get_client()
        prompt = CLASSIFY_PROMPT.format(message=message, channel=channel)

        response = client.models.generate_content(
            model=settings.gemini_model_fast,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,  # Deterministic cho classification
                max_output_tokens=1024,
            ),
        )

        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        
        result = json.loads(raw_text.strip())

        # Validate các field bắt buộc
        valid_classifications = {
            "info_inquiry", "complaint", "technical", "payment",
            "emergency", "spam", "missing_info", "human_requested",
        }
        if result.get("classification") not in valid_classifications:
            result["classification"] = "info_inquiry"

        valid_priorities = {"low", "medium", "high", "critical"}
        if result.get("priority") not in valid_priorities:
            result["priority"] = "medium"

        return {
            "classification": result["classification"],
            "priority": result["priority"],
            "has_sufficient_info": result.get("has_sufficient_info", True),
            "requires_human": result.get("requires_human", False),
            "reasoning": result.get("reasoning", ""),
        }

    except Exception as e:
        import traceback
        logger.error(f"Gemini classify error: {e}")
        logger.error(traceback.format_exc())
        # Fallback an toàn — escalate khi không chắc chắn
        return {
            "classification": "info_inquiry",
            "priority": "medium",
            "has_sufficient_info": True,
            "requires_human": False,
            "reasoning": f"Fallback do lỗi API: {e}",
        }


# ============================================================
# RAG Response generation prompt
# ============================================================
RAG_RESPONSE_PROMPT = """Bạn là nhân viên hỗ trợ khách hàng cho sàn thương mại điện tử.
Trả lời câu hỏi của khách hàng dựa vào tài liệu được cung cấp bên dưới (nếu có).
Nếu tài liệu không đủ thông tin hoặc không có tài liệu, bạn hãy dùng kiến thức chung về thương mại điện tử để giải đáp một cách thân thiện và chuyên nghiệp.

Quy tắc:
- Trả lời bằng tiếng Việt, thân thiện, chuyên nghiệp
- Nếu dùng tài liệu, hãy trích dẫn nguồn
- Không bịa mã số hay tên riêng nếu không chắc chắn

Tài liệu tham khảo:
{documents}

Câu hỏi khách hàng:
\"\"\"{message}\"\"\"
"""


def generate_rag_response(message: str, documents: list[dict]) -> str:
    """Gọi Gemini để sinh câu trả lời dựa trên tài liệu RAG.

    Args:
        message: Câu hỏi của khách hàng.
        documents: Danh sách tài liệu đã retrieve (mỗi doc có 'source' và 'content').

    Returns:
        Câu trả lời dạng text. Nếu API lỗi, trả về nội dung tài liệu trực tiếp.
    """
    try:
        client = _get_client()

        # Format tài liệu
        docs_text = ""
        for i, doc in enumerate(documents, 1):
            docs_text += f"\n[{i}] {doc.get('source', 'N/A')}:\n{doc.get('content', '')}\n"

        prompt = RAG_RESPONSE_PROMPT.format(documents=docs_text, message=message)

        response = client.models.generate_content(
            model=settings.gemini_model_quality,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,  # Hơi sáng tạo nhưng vẫn bám tài liệu
                max_output_tokens=2048,
            ),
        )

        return response.text.strip()

    except Exception as e:
        logger.error(f"Gemini RAG response error: {e}")
        # Fallback — trả nội dung tài liệu trực tiếp
        if documents:
            doc = documents[0]
            return (
                f"{doc.get('content', 'Không có thông tin.')}\n\n"
                f"📎 Nguồn: {doc.get('source', 'N/A')}"
            )
        return "Xin lỗi, hệ thống đang gặp sự cố. Vui lòng thử lại sau."


# ============================================================
# Embedding generation
# ============================================================
def get_embedding(text: str) -> list[float]:
    """Tạo vector embedding cho chuỗi text bằng Gemini.
    
    Dùng cho Qdrant (bước 4) để lưu trữ và tìm kiếm vector.
    """
    try:
        client = _get_client()
        response = client.models.embed_content(
            model="gemini-embedding-2",
            contents=text,
        )
        return response.embeddings[0].values
    except Exception as e:
        logger.error(f"Gemini embedding error: {e}")
        # Trả về vector zero nếu lỗi để hệ thống không sập
        return [0.0] * 3072

