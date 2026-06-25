"""QA 节点（纯 RAG，单步）—— 知识题专用。

跟 phase 2 的 ReAct 不同：不让 LLM 选工具，直接 retriever → context → LLM。
适用于 supervisor 已判定为"知识题"的场景。
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from loguru import logger

from ...core import AgentState, get_chat_llm
from ...memory import augment_question_with_memory
from ...rag import format_citations, make_retriever
from ..prompts import QA_SYSTEM_PROMPT, format_context


def qa_node(state: AgentState) -> dict:
    question = state.get("question", "").strip()
    if not question:
        return {"messages": [AIMessage(content="请提供问题。")]}

    retriever = make_retriever(top_k=5)
    docs = retriever.invoke(question)
    logger.info("qa_node 召回 {} 条", len(docs))

    context = format_context(docs)
    long_term_context = state.get("long_term_context", "")
    question_with_memory = augment_question_with_memory(question, long_term_context)
    response = get_chat_llm().invoke([
        SystemMessage(content=QA_SYSTEM_PROMPT),
        HumanMessage(content=f"【参考资料】\n{context}\n\n【问题】\n{question_with_memory}"),
    ])

    return {
        "messages": [response],
        "retrieved": [
            {
                "chunk_id": d.metadata.get("chunk_id"),
                "content": d.page_content,
                "score": d.metadata.get("score"),
                "metadata": {
                    k: v for k, v in d.metadata.items()
                    if k not in ("chunk_id", "score")
                },
            }
            for d in docs
        ],
        "citations": format_citations(docs),
    }
