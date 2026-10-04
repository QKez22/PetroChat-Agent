"""证据驱动 QA worker；未通过验证的模型草稿不进入消息流。"""

from __future__ import annotations

import re

from langchain_core.messages import AIMessage

from ...core import AgentState, get_settings
from ...rag.evidence import build_evidence_graph, render_result


def qa_node(state: AgentState) -> dict:
    question = state.get("question", "").strip()
    historical = re.search(r"历史|当时|那年|去年|前年|20\d{2}年|20\d{2}-\d", question)
    if not question or (historical and not state.get("rag_as_of")):
        return {
            "messages": [
                AIMessage(content="请补充问题及明确的规范适用日期（rag_as_of），避免混用历史版本。")
            ],
            "retrieved": [],
            "citations": [],
            "rag_status": "needs_clarification",
            "evidence": [],
        }
    if state.get("rag_as_of") and not get_settings().rag_catalog_enabled:
        return {
            "messages": [AIMessage(content="版本策略尚未启用，无法核实指定日期的适用规范。")],
            "retrieved": [],
            "citations": [],
            "rag_status": "needs_review",
            "evidence": [],
        }
    result = render_result(
        build_evidence_graph().invoke({"question": question}, {"recursion_limit": 12})
    )
    answer = result.pop("answer")
    return {**result, "messages": [AIMessage(content=answer)]}
