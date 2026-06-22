"""问答节点：检索 → 组 prompt → LLM 生成答案。

LangGraph 节点的本质：(state) -> partial_state
  - 接收当前共享状态
  - 做完工作后返回 dict，LangGraph 会把它合并进 state
  - **不直接修改 state**，遵守纯函数风格（便于调试和 checkpoint）
"""

from __future__ import annotations

from loguru import logger

from ...core import AgentState, get_chat_llm
from ...rag import format_citations, make_retriever
from ..prompts import QA_PROMPT, format_context


def qa_node(state: AgentState) -> dict:
    """RAG 问答节点。

    输入 state["question"]，输出更新到：
      - state["retrieved"]: 原始召回片段（含 content/metadata/score）
      - state["answer"]:    LLM 生成的答案文本
      - state["citations"]: 用户可读的引用串列表
    """
    question = state.get("question", "").strip()
    if not question:
        return {"answer": "请提供问题。", "retrieved": [], "citations": []}

    # 1. 检索
    logger.info("qa_node 检索: {}", question)
    retriever = make_retriever(top_k=5)
    docs = retriever.invoke(question)
    logger.info("qa_node 召回 {} 条 (top score={:.4f})",
                len(docs),
                docs[0].metadata.get("score", -1) if docs else -1)

    # 2. 组 prompt
    context = format_context(docs)
    messages = QA_PROMPT.format_messages(context=context, question=question)

    # 3. 调 LLM
    llm = get_chat_llm()
    response = llm.invoke(messages)
    answer = response.content if hasattr(response, "content") else str(response)

    # 4. 整理返回
    return {
        "retrieved": [
            {
                "chunk_id": d.metadata.get("chunk_id"),
                "content": d.page_content,
                "score": d.metadata.get("score"),
                "metadata": {k: v for k, v in d.metadata.items()
                             if k not in ("chunk_id", "score")},
            }
            for d in docs
        ],
        "answer": answer,
        "citations": format_citations(docs),
    }
