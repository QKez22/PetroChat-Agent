"""FastAPI 路由：问答接口（同步 + SSE 流式）。

Phase 2 更新：
  - graph 改为 ReAct，主状态在 state["messages"]
  - 答案 = 最后一条 AIMessage 的 content
  - citations 从答案文本中正则抽取 [N.N.N] 模式
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from ..agent import build_graph, build_initial_state
from ..core.models import ChatRequest, ChatResponse

router = APIRouter(prefix="/api", tags=["chat"])

# 用于从答案文本里抽取 [N.N.N] 形式的章节号引用
_CITATION_PAT = re.compile(r"\[(\d+(?:\.\d+){1,3})\]")


def _extract_answer_and_citations(state: dict) -> tuple[str, list[str]]:
    """从 ReAct 图的最终 state 中抽取答案与引用编号。"""
    msgs = state.get("messages") or []
    answer = ""
    # 最后一条不含 tool_calls 的 AIMessage 即最终答案
    for m in reversed(msgs):
        if isinstance(m, AIMessage) and m.content and not getattr(m, "tool_calls", None):
            answer = m.content if isinstance(m.content, str) else str(m.content)
            break

    citations = list(dict.fromkeys(_CITATION_PAT.findall(answer)))  # 保序去重
    return answer, citations


# ============================================================
# 非流式接口
# ============================================================
@router.post("/chat", response_model=ChatResponse, summary="问答（非流式）")
async def chat(req: ChatRequest) -> ChatResponse:
    graph = build_graph()
    try:
        result = await graph.ainvoke(build_initial_state(req.question))
    except Exception as e:
        logger.exception("graph.ainvoke 失败")
        raise HTTPException(status_code=500, detail=str(e)) from e

    answer, citations = _extract_answer_and_citations(result)
    return ChatResponse(answer=answer, citations=citations, score=None)


# ============================================================
# SSE 流式接口
# ============================================================
def _sse(event: str, data: dict[str, Any]) -> dict[str, str]:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


async def _stream_events(question: str) -> AsyncGenerator[dict[str, str], None]:
    """把 LangGraph 事件流翻译成 SSE 事件流。

    SSE 事件类型：
      token       LLM 每个文本 chunk（最频繁）
      tool_call   LLM 决定调工具时（含工具名 + 参数，让前端可显示"思考中..."）
      tool_result 工具返回时（含工具名 + 截断的结果）
      meta        全流程结束时（含 citations）
      done        流结束
      error       任一环节抛错
    """
    graph = build_graph()
    state = build_initial_state(question)
    final_answer = ""

    try:
        async for event in graph.astream_events(state, version="v2"):
            kind = event.get("event")

            # ---- LLM token 流（最频繁）----
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                    final_answer += text
                    yield _sse("token", {"text": text})

            # ---- LLM 决定调工具 ----
            elif kind == "on_chat_model_end":
                output = event.get("data", {}).get("output")
                if isinstance(output, AIMessage) and getattr(output, "tool_calls", None):
                    for tc in output.tool_calls:
                        yield _sse("tool_call", {
                            "name": tc.get("name"),
                            "args": tc.get("args"),
                        })

            # ---- 工具执行完成 ----
            elif kind == "on_tool_end":
                tool_name = event.get("name")
                output = event.get("data", {}).get("output")
                result_text = ""
                if isinstance(output, ToolMessage):
                    result_text = output.content if isinstance(output.content, str) else str(output.content)
                elif isinstance(output, str):
                    result_text = output
                yield _sse("tool_result", {
                    "name": tool_name,
                    "preview": result_text[:200],
                })

        # 整图结束后从累积答案抽 citations
        citations = list(dict.fromkeys(_CITATION_PAT.findall(final_answer)))
        yield _sse("meta", {"citations": citations})
        yield _sse("done", {})

    except Exception as e:
        logger.exception("SSE 流处理失败")
        yield _sse("error", {"message": str(e)})


@router.post("/chat/stream", summary="问答（SSE 流式）")
async def chat_stream(req: ChatRequest) -> EventSourceResponse:
    return EventSourceResponse(_stream_events(req.question))
