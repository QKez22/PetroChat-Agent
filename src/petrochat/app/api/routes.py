"""FastAPI 路由：问答接口（同步 + SSE 流式）。

接口设计：
  POST /api/chat         非流式，返回完整答案（适合脚本/测试）
  POST /api/chat/stream  SSE 流式，按 token 推送（适合前端聊天界面）

SSE 事件类型：
  event: token   data: {"text": "..."}        # LLM 输出的每个 token chunk
  event: meta    data: {"retrieved": [...], "citations": [...]}  # 检索结果与引用
  event: done    data: {}                     # 流结束
  event: error   data: {"message": "..."}     # 任一环节抛错
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessageChunk
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from ..agent import build_graph
from ..core.models import ChatRequest, ChatResponse

router = APIRouter(prefix="/api", tags=["chat"])


# ============================================================
# 非流式接口（Swagger 友好，给脚本/测试用）
# ============================================================
@router.post("/chat", response_model=ChatResponse, summary="问答（非流式）")
async def chat(req: ChatRequest) -> ChatResponse:
    """一次性返回完整答案与引用。

    内部仍走 graph.ainvoke，只是把流合并成最终结果再回给客户端。
    """
    graph = build_graph()
    try:
        result = await graph.ainvoke({"question": req.question})
    except Exception as e:
        logger.exception("graph.ainvoke 失败")
        raise HTTPException(status_code=500, detail=str(e)) from e

    return ChatResponse(
        answer=result.get("answer", ""),
        citations=result.get("citations") or [],
        # 第一阶段不带评分，留 None
        score=None,
    )


# ============================================================
# SSE 流式接口
# ============================================================
def _sse_event(event: str, data: dict[str, Any]) -> dict[str, str]:
    """格式化为 sse-starlette 接受的字典形式。"""
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


async def _stream_events(question: str) -> AsyncGenerator[dict[str, str], None]:
    """把 LangGraph 的事件流翻译成 SSE 事件流。

    依赖 ChatOpenAI(streaming=True) 把 LLM 的 token chunks 通过 callback 冒泡，
    astream_events(version="v2") 接住它们再分发。
    """
    graph = build_graph()
    state = {"question": question}

    # 缓存检索完成后的 docs 和最终 state，结束时一并 emit
    retrieved_docs: list[dict[str, Any]] = []
    citations: list[str] = []

    try:
        async for event in graph.astream_events(state, version="v2"):
            kind = event.get("event")

            # ---- LLM token 流（最频繁的事件）----
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    yield _sse_event("token", {"text": chunk.content})

            # ---- 检索完成 ----
            elif kind == "on_retriever_end":
                output = event.get("data", {}).get("output", [])
                retrieved_docs = [
                    {
                        "chunk_id": d.metadata.get("chunk_id"),
                        "section_number": d.metadata.get("section_number"),
                        "source_doc": d.metadata.get("source_doc"),
                        "score": d.metadata.get("score"),
                        "content_preview": d.page_content[:120],
                    }
                    for d in output
                ]

            # ---- 整个 graph 结束，从最终 state 拿 citations ----
            elif kind == "on_chain_end" and event.get("name") == "LangGraph":
                output = event.get("data", {}).get("output", {})
                citations = output.get("citations") or []

        # 节点流结束，统一推送 meta + done
        yield _sse_event("meta", {
            "retrieved": retrieved_docs,
            "citations": citations,
        })
        yield _sse_event("done", {})

    except Exception as e:
        logger.exception("SSE 流处理失败")
        yield _sse_event("error", {"message": str(e)})


@router.post("/chat/stream", summary="问答（SSE 流式）")
async def chat_stream(req: ChatRequest) -> EventSourceResponse:
    """SSE 流式问答。

    前端用法（JavaScript）：
        const resp = await fetch("/api/chat/stream", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({question: "..."}),
        });
        const reader = resp.body.getReader();
        ...
    （后续 1.9 之后会给前端示例代码）
    """
    return EventSourceResponse(_stream_events(req.question))
