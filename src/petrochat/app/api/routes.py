"""FastAPI 路由：问答接口（同步 + SSE 流式）。

Phase 2 更新：
  - graph 改为 ReAct，主状态在 state["messages"]
  - 答案 = 最后一条 AIMessage 的 content
  - citations 从答案文本中正则抽取 [N.N.N] 模式
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from ..agent import build_graph, build_initial_state
from ..core import get_settings
from ..core.models import (
    ChatMessageRecord,
    ChatRequest,
    ChatResponse,
    SessionDetail,
    SessionSummary,
)
from ..memory import StoredMessage, get_conversation_store

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


def _to_history_payload(messages: list[StoredMessage]) -> list[dict[str, str]]:
    """转成 build_initial_state 需要的轻量历史消息。"""
    return [{"role": m.role, "content": m.content} for m in messages if m.content]


def _guess_route(state: dict, answer: str) -> str:
    nxt = state.get("next")
    if nxt in {"qa", "sql", "general"}:
        return str(nxt)
    if state.get("retrieved") or _CITATION_PAT.findall(answer):
        return "qa"
    return "general"


# ============================================================
# 非流式接口
# ============================================================
@router.post("/chat", response_model=ChatResponse, summary="问答（非流式）")
async def chat(req: ChatRequest) -> ChatResponse:
    graph = build_graph()
    store = get_conversation_store()
    settings = get_settings()
    session_id = store.ensure_session(req.session_id, user_id=req.user_id, title=req.question[:80])
    history = _to_history_payload(store.recent_messages(session_id, settings.short_term_turns))
    started_at = time.perf_counter()
    try:
        result = await graph.ainvoke(
            build_initial_state(
                req.question,
                session_id=session_id,
                user_id=req.user_id,
                history=history,
            )
        )
    except Exception as e:
        logger.exception("graph.ainvoke 失败")
        raise HTTPException(status_code=500, detail=str(e)) from e

    answer, citations = _extract_answer_and_citations(result)
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    store.append_turn(
        session_id,
        req.question,
        answer,
        route=_guess_route(result, answer),
        latency_ms=latency_ms,
    )
    return ChatResponse(answer=answer, citations=citations, score=None, session_id=session_id)


# ============================================================
# SSE 流式接口
# ============================================================
def _sse(event: str, data: dict[str, Any]) -> dict[str, str]:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


async def _stream_events(req: ChatRequest) -> AsyncGenerator[dict[str, str], None]:
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
    store = get_conversation_store()
    settings = get_settings()
    session_id = store.ensure_session(req.session_id, user_id=req.user_id, title=req.question[:80])
    history = _to_history_payload(store.recent_messages(session_id, settings.short_term_turns))
    state = build_initial_state(
        req.question,
        session_id=session_id,
        user_id=req.user_id,
        history=history,
    )
    final_answer = ""
    route = "general"
    started_at = time.perf_counter()

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
                        if tc.get("name") == "RouteDecision":
                            args = tc.get("args") or {}
                            if args.get("next") in {"qa", "sql", "general"}:
                                route = args["next"]
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

        # 整图结束后从累积答案抽 citations + 拿走最近一次报表（含 chart 的 data URI）
        citations = list(dict.fromkeys(_CITATION_PAT.findall(final_answer)))
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        if final_answer.strip():
            store.append_turn(
                session_id,
                req.question,
                final_answer,
                route=route,
                latency_ms=latency_ms,
            )

        meta: dict[str, Any] = {
            "citations": citations,
            "session_id": session_id,
            "short_term_count": len(history),
        }

        try:
            from ..report import pop_last_report
            rep = pop_last_report()
            if rep and rep.chart_data_uri:
                meta["chart_data_uri"] = rep.chart_data_uri
                meta["chart_kind"] = rep.chart_kind
                meta["table_row_count"] = rep.row_count
        except Exception as e:
            logger.warning("拉取 last_report 失败: {}", e)

        yield _sse("meta", meta)
        yield _sse("done", {})

    except Exception as e:
        logger.exception("SSE 流处理失败")
        yield _sse("error", {"message": str(e)})


@router.post("/chat/stream", summary="问答（SSE 流式）")
async def chat_stream(req: ChatRequest) -> EventSourceResponse:
    return EventSourceResponse(_stream_events(req))


@router.get("/sessions", response_model=list[SessionSummary], summary="会话列表")
async def list_sessions(user_id: str = "default", limit: int = 30) -> list[SessionSummary]:
    store = get_conversation_store()
    return [SessionSummary(**row) for row in store.list_sessions(user_id=user_id, limit=limit)]


@router.get("/sessions/{session_id}", response_model=SessionDetail, summary="会话详情")
async def get_session(session_id: str, user_id: str = "default") -> SessionDetail:
    store = get_conversation_store()
    sessions = [row for row in store.list_sessions(user_id=user_id, limit=500) if row["id"] == session_id]
    if not sessions:
        raise HTTPException(status_code=404, detail="session not found")
    messages = [
        ChatMessageRecord(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,  # type: ignore[arg-type]
            content=m.content,
            route=m.route,
            latency_ms=m.latency_ms,
            created_at=m.created_at,
        )
        for m in store.list_messages(session_id)
    ]
    return SessionDetail(session=SessionSummary(**sessions[0]), messages=messages)


@router.delete("/sessions/{session_id}", summary="删除会话")
async def delete_session(session_id: str, user_id: str | None = None) -> dict[str, bool]:
    store = get_conversation_store()
    if user_id:
        sessions = [row for row in store.list_sessions(user_id=user_id, limit=500) if row["id"] == session_id]
        if not sessions:
            raise HTTPException(status_code=404, detail="session not found")
    deleted = store.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="session not found")
    return {"deleted": True}
