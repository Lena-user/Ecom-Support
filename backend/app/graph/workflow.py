"""LangGraph workflow — dựng state graph với conditional edges.

Luồng xử lý:
    START → ingest → check_duplicate
        ├─ trùng → respond → END
        └─ không trùng → classify
            ├─ spam → handle_spam → END
            ├─ thiếu thông tin → ask_info → END
            ├─ khiếu nại/thanh toán/khẩn cấp/yêu cầu người → escalate → END
            └─ hỏi đáp/kỹ thuật → rag_respond
                ├─ similarity đủ → respond → END
                └─ similarity thấp → escalate → END
"""

from langgraph.graph import END, START, StateGraph

from app.graph import nodes
from app.graph.state import SupportState


def build_workflow() -> StateGraph:
    """Xây dựng và compile graph.

    Returns:
        Compiled LangGraph workflow, gọi .invoke(state) để chạy.
    """
    graph = StateGraph(SupportState)

    # ---- Đăng ký nodes ----
    graph.add_node("ingest", nodes.ingest)
    graph.add_node("check_duplicate", nodes.check_duplicate)
    graph.add_node("classify", nodes.classify)
    graph.add_node("handle_spam", nodes.handle_spam)
    graph.add_node("ask_info", nodes.ask_info)
    graph.add_node("rag_respond", nodes.rag_respond)
    graph.add_node("escalate", nodes.escalate)
    graph.add_node("respond", nodes.respond)

    # ---- Edges cố định ----
    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "check_duplicate")

    # ---- Conditional edges ----
    # Sau duplicate check
    graph.add_conditional_edges(
        "check_duplicate",
        nodes.after_duplicate_check,
        {"respond": "respond", "classify": "classify"},
    )

    # Sau classification → routing
    graph.add_conditional_edges(
        "classify",
        nodes.after_classify,
        {
            "handle_spam": "handle_spam",
            "ask_info": "ask_info",
            "escalate": "escalate",
            "rag_respond": "rag_respond",
        },
    )

    # Sau RAG → similarity gate
    graph.add_conditional_edges(
        "rag_respond",
        nodes.after_rag,
        {"respond": "respond", "escalate": "escalate"},
    )

    # ---- Terminal edges → END ----
    graph.add_edge("handle_spam", END)
    graph.add_edge("ask_info", END)
    graph.add_edge("escalate", END)
    graph.add_edge("respond", END)

    return graph.compile()


# Singleton — dùng chung cho toàn app
workflow = build_workflow()
