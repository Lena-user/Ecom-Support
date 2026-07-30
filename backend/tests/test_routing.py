"""Unit test cho các hàm routing thuần trong app.graph.nodes — không cần mock gì
vì đây là pure function, chỉ đọc state dict và trả về tên node tiếp theo.
"""

import pytest

from app.graph.nodes import after_classify, after_duplicate_check, after_rag


def test_after_duplicate_check_routes_to_respond_when_duplicate():
    assert after_duplicate_check({"is_duplicate": True}) == "respond"


def test_after_duplicate_check_routes_to_classify_when_not_duplicate():
    assert after_duplicate_check({"is_duplicate": False}) == "classify"


@pytest.mark.parametrize(
    "classification, has_sufficient_info, requires_human, expected",
    [
        # Spam luôn bị lọc, bất kể requires_human
        ("spam", True, False, "handle_spam"),
        # Thiếu thông tin -> hỏi lại, dù phân loại là gì
        ("missing_info", True, False, "ask_info"),
        ("info_inquiry", False, False, "ask_info"),
        # Các loại luôn cần escalate
        ("complaint", True, False, "escalate"),
        ("payment", True, False, "escalate"),
        ("emergency", True, False, "escalate"),
        ("human_requested", True, False, "escalate"),
        # requires_human=True cũng escalate dù phân loại là info_inquiry
        ("info_inquiry", True, True, "escalate"),
        # Còn lại -> thử RAG
        ("info_inquiry", True, False, "rag_respond"),
        ("technical", True, False, "rag_respond"),
    ],
)
def test_after_classify_routes_correctly(classification, has_sufficient_info, requires_human, expected):
    state = {
        "classification": classification,
        "has_sufficient_info": has_sufficient_info,
        "requires_human": requires_human,
    }
    assert after_classify(state) == expected


def test_after_rag_routes_to_respond_when_gemini_confirms_sufficient_grounding():
    assert after_rag({"rag_has_sufficient_grounding": True}) == "respond"


def test_after_rag_routes_to_escalate_when_gemini_says_insufficient():
    """Gemini tự đánh giá không đủ căn cứ tài liệu → phải chuyển nhân viên,
    không được tự trả lời bằng kiến thức chung (an toàn theo yêu cầu đề bài)."""
    assert after_rag({"rag_has_sufficient_grounding": False}) == "escalate"
