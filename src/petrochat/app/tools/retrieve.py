"""RAG-as-tool：把语义检索包装成 LLM 可调用的工具。

为什么把 RAG 也包装成工具？
  这是 ReAct 架构的核心思想 —— **让 LLM 自己决定何时检索**。
  对"1 MPa 等于多少 psi"这种纯计算题，根本不需要检索；
  对"什么是 ITPM 策略"这种领域题，LLM 应主动调用 retrieve_specs。
  对比 phase 1 的"无条件先检索"，这是更"agentic"的形态。
"""

from __future__ import annotations

from langchain_core.tools import tool

from ..rag import format_citation, make_retriever


@tool
def retrieve_specs(query: str, top_k: int = 5) -> str:
    """在石化规范知识库中做语义检索。

    适用：用户问的是规范条款内容、定义、术语、流程等需要查阅文档的问题。

    Args:
        query: 自然语言查询，尽量包含关键词（如"ITPM 策略""设备分级"）
        top_k: 返回条数，默认 5

    Returns:
        相关条款的拼接文本，每条前置 [章节号 出自《xxx》]，便于 LLM 在答案中引用。
    """
    docs = make_retriever(top_k=top_k).invoke(query)
    if not docs:
        return "（未在知识库中找到相关条款。）"

    parts = []
    for d in docs:
        cite = format_citation(d.metadata)
        sec = d.metadata.get("section_number", "")
        # 章节号放最前面，方便 LLM 写 [4.2.2] 这种引用
        parts.append(f"[{sec} {cite}]\n{d.page_content}")
    return "\n\n---\n\n".join(parts)
