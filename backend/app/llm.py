"""Gemini LLM client — wrapper cho Google GenAI SDK.

Cung cấp 2 hàm chính:
- classify_message(): Phân loại yêu cầu (dùng model nhanh)
- generate_rag_response(): Sinh câu trả lời từ tài liệu (dùng model chất lượng)
"""

import json
import logging

import tenacity
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


# Retry cho lỗi tạm thời (503 UNAVAILABLE, 429 RESOURCE_EXHAUSTED, network...) —
# thử tối đa 3 lần với backoff tăng dần trước khi để except bên ngoài fallback.
_retry_gemini_call = tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)


@_retry_gemini_call
def _generate_content(client: genai.Client, **kwargs):
    return client.models.generate_content(**kwargs)


@_retry_gemini_call
def _embed_content(client: genai.Client, **kwargs):
    return client.models.embed_content(**kwargs)


# ============================================================
# Classification prompt
# ============================================================
CLASSIFY_PROMPT = """Bạn là hệ thống phân loại yêu cầu khách hàng cho sàn thương mại điện tử.

Phân loại tin nhắn sau vào ĐÚNG 1 trong các loại:
- "info_inquiry": Hỏi đáp thông tin (chính sách, thời gian giao hàng, mã giảm giá, hướng dẫn chung)
- "complaint": Khiếu nại (hàng lỗi, giao sai, giao chậm, không đúng mô tả)
- "technical": Yêu cầu kỹ thuật (lỗi app, không đăng nhập được, lỗi thanh toán kỹ thuật)
- "payment": Yêu cầu thanh toán nhạy cảm (hoàn tiền, tranh chấp giao dịch, mất tiền)
- "emergency": Khẩn cấp (gian lận, tài khoản bị hack, lừa đảo)
- "spam": Tin rác, quảng cáo, nội dung không liên quan
- "missing_info": Thiếu thông tin để xử lý (tin nhắn mơ hồ, không rõ yêu cầu)
- "human_requested": Khách hàng chủ động yêu cầu gặp nhân viên / người thật

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
    "requires_human": true/false,
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

        response = _generate_content(
            client,
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
Đọc kỹ câu hỏi khách hàng và các tài liệu tham khảo bên dưới (nếu có), sau đó:
1. Trả lời câu hỏi CHỈ dựa trên các tài liệu được cung cấp — không bịa thêm thông tin.
2. Tự đánh giá xem tài liệu có đủ căn cứ để trả lời CHÍNH XÁC câu hỏi hay không.

Quy tắc:
- Trả lời bằng tiếng Việt, thân thiện, chuyên nghiệp
- CHỈ dùng thông tin từ tài liệu, KHÔNG bịa thêm
- Nếu dùng tài liệu để trả lời, trích dẫn nguồn ở cuối câu trả lời
- has_sufficient_grounding = false nếu tài liệu không liên quan, không đủ chi tiết, hoặc câu
  hỏi vượt ngoài phạm vi các tài liệu được cung cấp. Khi đó "answer" phải là một câu xin lỗi
  ngắn gọn và cho biết yêu cầu sẽ được chuyển cho nhân viên hỗ trợ — KHÔNG được tự bịa câu
  trả lời bằng kiến thức chung.

Tài liệu tham khảo:
{documents}

Câu hỏi khách hàng:
\"\"\"{message}\"\"\"

Trả về JSON với format:
{{
    "answer": "<câu trả lời>",
    "has_sufficient_grounding": true/false,
    "reasoning": "<giải thích ngắn gọn vì sao đủ/không đủ căn cứ>"
}}
"""


def generate_rag_response(message: str, documents: list[dict]) -> dict:
    """Gọi Gemini để sinh câu trả lời dựa trên tài liệu RAG, đồng thời để Gemini
    tự đánh giá xem tài liệu có đủ căn cứ để trả lời chính xác hay không.

    Args:
        message: Câu hỏi của khách hàng.
        documents: Danh sách tài liệu đã retrieve (mỗi doc có 'source' và 'content').

    Returns:
        Dict {"answer": str, "has_sufficient_grounding": bool, "reasoning": str}.
        Nếu API lỗi, has_sufficient_grounding=False (an toàn — chuyển người khi không chắc chắn).
    """
    try:
        client = _get_client()

        # Format tài liệu
        docs_text = ""
        for i, doc in enumerate(documents, 1):
            docs_text += f"\n[{i}] {doc.get('source', 'N/A')}:\n{doc.get('content', '')}\n"
        if not docs_text:
            docs_text = "(Không tìm thấy tài liệu nào liên quan)"

        prompt = RAG_RESPONSE_PROMPT.format(documents=docs_text, message=message)

        response = _generate_content(
            client,
            model=settings.gemini_model_quality,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,  # Hơi sáng tạo nhưng vẫn bám tài liệu
                max_output_tokens=2048,
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

        return {
            "answer": result.get("answer", "Xin lỗi, hệ thống chưa thể trả lời câu hỏi này."),
            "has_sufficient_grounding": bool(result.get("has_sufficient_grounding", False)),
            "reasoning": result.get("reasoning", ""),
        }

    except Exception as e:
        logger.error(f"Gemini RAG response error: {e}")
        # Fallback an toàn — không chắc chắn thì phải chuyển người, không tự bịa
        return {
            "answer": (
                "Xin lỗi, hệ thống đang gặp sự cố khi xử lý câu hỏi của bạn. "
                "Yêu cầu của bạn sẽ được chuyển cho nhân viên hỗ trợ."
            ),
            "has_sufficient_grounding": False,
            "reasoning": f"Lỗi hệ thống khi gọi Gemini: {e}",
        }


# ============================================================
# Embedding generation
# ============================================================
def get_embedding(text: str) -> list[float]:
    """Tạo vector embedding cho chuỗi text bằng Gemini.
    
    Dùng cho Qdrant (bước 4) để lưu trữ và tìm kiếm vector.
    """
    try:
        client = _get_client()
        response = _embed_content(
            client,
            model="gemini-embedding-2",
            contents=text,
        )
        return response.embeddings[0].values
    except Exception as e:
        logger.error(f"Gemini embedding error: {e}")
        # Trả về vector zero nếu lỗi để hệ thống không sập
        return [0.0] * 3072
