"""FastAPI 问答接口: 共用最终结果, SSE 只发送 worker 正文与工具进度。"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage, ToolMessage
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from ..agent import build_graph, build_initial_state
from ..agent.result import CITATION_PATTERN, answer_parts, build_turn_result
from ..core import get_settings
from ..core.models import (
    ChatMessageRecord,
    ChatRequest,
    ChatResponse,
    SessionDetail,
    SessionSummary,
)
from ..memory import (
    StoredMessage,
    fit_prompt_context,
    get_conversation_store,
    recall_long_term_memories,
    refresh_conversation_summary,
    write_memory_candidates,
)
from .auth import CurrentUserDep

router = APIRouter(prefix="/api", tags=["chat"])

_CITATION_PAT = CITATION_PATTERN


def _extract_answer_and_citations(state: dict) -> tuple[str, list[str]]:
    result = build_turn_result(state)
    return result.answer, result.citations


def _to_history_payload(messages: list[StoredMessage]) -> list[dict[str, str]]:
    """转成 build_initial_state 需要的轻量历史消息。"""
    return [{"role": m.role, "content": m.content} for m in messages if m.content]


def _guess_route(state: dict, answer: str) -> str:
    nxt = state.get("next")
    if nxt in {"qa", "sql", "general"}:
        return str(nxt)
    # 循环 supervisor FINISH 后 next 不反映实际路由，按 state 产出推断
    if state.get("sql_result"):
        return "sql"
    if state.get("retrieved") or _CITATION_PAT.findall(answer):
        return "qa"
    return "general"


def _resolve_user_id(requested_user_id: str | None, user: CurrentUserDep) -> str:
    """Resolve effective user id from JWT; admins may choose another user."""

    requested = (requested_user_id or "").strip()
    if user.role == "admin" and requested and requested != "default":
        return requested
    if requested and requested not in {"default", user.user_id}:
        raise HTTPException(status_code=403, detail="cannot access another user's data")
    return user.user_id


def _memory_recall_summary(memories: list[Any]) -> dict[str, Any]:
    mysql_count = sum(1 for mem in memories if getattr(mem, "recall_source", "") == "mysql")
    mem0_count = sum(1 for mem in memories if getattr(mem, "recall_source", "") == "mem0")
    ids = [getattr(mem, "memory_id", getattr(mem, "id", "")) for mem in memories]
    return {
        "total": len(memories),
        "mysql": mysql_count,
        "mem0": mem0_count,
        "injected": len(memories),
        "ids": ids,
        "mysql_count": mysql_count,
        "mem0_count": mem0_count,
        "injected_count": len(memories),
        "items": [
            {
                "memory_id": getattr(mem, "memory_id", getattr(mem, "id", "")),
                "content": getattr(mem, "content", ""),
                "source": getattr(mem, "recall_source", "mysql"),
                "score": getattr(mem, "score", None),
            }
            for mem in memories
        ],
    }


def _conversation_summary_text(store: Any, session_id: str) -> str:
    try:
        summary = store.get_summary(session_id)
    except Exception as exc:
        logger.warning("conversation summary load failed: {}", exc)
        return ""
    return summary.summary_text if summary else ""


def _refresh_summary_after_turn(store: Any, session_id: str) -> None:
    try:
        refresh_conversation_summary(session_id, store=store)
    except Exception as exc:
        logger.warning("conversation summary refresh failed: {}", exc)


# ============================================================
# 非流式接口
# ============================================================
@router.post("/chat", response_model=ChatResponse, summary="问答（非流式）")
async def chat(req: ChatRequest, user: CurrentUserDep) -> ChatResponse:
    started_at = time.perf_counter()
    try:
        graph = build_graph()
        store = get_conversation_store()
        settings = get_settings()
        user_id = _resolve_user_id(req.user_id, user)
        session_id = store.ensure_session(req.session_id, user_id=user_id, title=req.question[:80])
        history = _to_history_payload(store.recent_messages(session_id, settings.short_term_turns))
        conversation_summary = _conversation_summary_text(store, session_id)
        memories, memory_context = recall_long_term_memories(
            user_id=user_id,
            question=req.question,
            limit=settings.long_term_memory_limit,
        )
        prompt_context = fit_prompt_context(
            question=req.question,
            history=history,
            conversation_summary=conversation_summary,
            long_term_context=memory_context,
        )
        result = await graph.ainvoke(
            build_initial_state(
                req.question,
                session_id=session_id,
                user_id=user_id,
                history=prompt_context.history,
                conversation_summary=prompt_context.conversation_summary,
                long_term_memories=[m.to_state() for m in memories],
                long_term_context=prompt_context.long_term_context,
            )
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("graph.ainvoke 失败")
        raise HTTPException(status_code=500, detail=_friendly_error_message(e)) from e

    turn_result = build_turn_result(result)
    answer, citations = turn_result.answer, turn_result.citations
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    route = _guess_route(result, answer)
    store.append_turn(
        session_id,
        req.question,
        answer,
        route=route,
        latency_ms=latency_ms,
    )
    _refresh_summary_after_turn(store, session_id)
    written = write_memory_candidates(user_id=user_id, question=req.question, answer=answer, route=route)
    return ChatResponse(
        answer=answer,
        citations=citations,
        artifacts=turn_result.artifacts,
        score=None,
        session_id=session_id,
        memory_used=[m.id for m in memories],
        memory_written=[m.id for m in written],
        memory_recall={
            **_memory_recall_summary(memories),
            "prompt_estimated_tokens": prompt_context.estimated_tokens,
            "dropped_history_count": prompt_context.dropped_history_count,
        },
    )


# ============================================================
# SSE 流式接口
# ============================================================
def _sse(event: str, data: dict[str, Any]) -> dict[str, str]:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


def _friendly_error_message(exc: Exception) -> str:
    """把常见基础设施错误转成前端可读提示，详细堆栈仍保留在日志里。"""
    raw = str(exc)
    if "INSERT command denied" in raw and "agent_" in raw:
        return (
            "应用库账号没有 agent_* 表写权限。请配置 MYSQL_APP_USER/MYSQL_APP_PASSWORD，"
            "或给应用账号授予 agent_conversation、agent_message 等应用表的 CRUD 权限。"
        )
    return raw


async def _stream_events(req: ChatRequest, user: CurrentUserDep) -> AsyncGenerator[dict[str, str], None]:
    """把 LangGraph 事件流翻译成 SSE 事件流。

    SSE 事件类型：
      token       已完成 worker 的答案片段
      tool_call   LLM 决定调工具时（含工具名 + 参数，让前端可显示"思考中..."）
      tool_result 工具返回时（含工具名 + 截断的结果）
      result      与非流式一致的最终答案、引用及报表
      meta        全流程结束时（含 citations）
      done        流结束
      error       任一环节抛错
    """
    final_state = None
    emitted_parts = []
    started_at = time.perf_counter()

    try:
        graph = build_graph()
        store = get_conversation_store()
        settings = get_settings()
        user_id = _resolve_user_id(req.user_id, user)
        session_id = store.ensure_session(req.session_id, user_id=user_id, title=req.question[:80])
        history = _to_history_payload(store.recent_messages(session_id, settings.short_term_turns))
        conversation_summary = _conversation_summary_text(store, session_id)
        memories, memory_context = recall_long_term_memories(
            user_id=user_id,
            question=req.question,
            limit=settings.long_term_memory_limit,
        )
        prompt_context = fit_prompt_context(
            question=req.question,
            history=history,
            conversation_summary=conversation_summary,
            long_term_context=memory_context,
        )
        state = build_initial_state(
            req.question,
            session_id=session_id,
            user_id=user_id,
            history=prompt_context.history,
            conversation_summary=prompt_context.conversation_summary,
            long_term_memories=[m.to_state() for m in memories],
            long_term_context=prompt_context.long_term_context,
        )

        async for event in graph.astream_events(state, version="v2"):
            kind = event.get("event")
            name = event.get("name")
            parents = event.get("parent_ids", [])
            output = event.get("data", {}).get("output")

            # 只在顶层 worker 完成后交付正文, 不泄露 SQL 生成和路由模型文本。
            if kind == "on_chain_end":
                if not parents:
                    final_state = output
                elif len(parents) == 1 and name in {"qa", "sql", "general"} and isinstance(output, dict):
                    for part in answer_parts(output.get("messages") or []):
                        prefix = "\n\n" if emitted_parts else ""
                        emitted_parts.append(part)
                        yield _sse("token", {"text": prefix + part})
            elif kind == "on_chain_start" and len(parents) == 1 and name in {"qa", "sql", "general"}:
                yield _sse("progress", {"node": name})
            elif kind == "on_chat_model_end" and isinstance(output, AIMessage):
                # Supervisor/SQL 的结构化输出属于内部控制, 不是用户工具调用。
                if event.get("metadata", {}).get("langgraph_node") == "general":
                    for tc in output.tool_calls:
                        yield _sse("tool_call", {"name": tc.get("name"), "args": tc.get("args")})
            elif kind == "on_tool_end":
                content = output.content if isinstance(output, ToolMessage) else output
                preview = content if isinstance(content, str) else ""
                yield _sse("tool_result", {"name": name, "preview": preview[:200]})

        if not isinstance(final_state, dict):
            raise RuntimeError("未收到完整执行结果, 请重试")
        turn_result = build_turn_result(final_state)
        final_answer, citations = turn_result.answer, turn_result.citations
        route = _guess_route(final_state, final_answer)
        # 最终结果是权威值: 前端替换正文, 与非流式响应及落库保持一致。
        yield _sse("result", turn_result.model_dump())
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        if final_answer.strip():
            store.append_turn(
                session_id,
                req.question,
                final_answer,
                route=route,
                latency_ms=latency_ms,
            )
            _refresh_summary_after_turn(store, session_id)
        written = write_memory_candidates(user_id=user_id, question=req.question, answer=final_answer, route=route)

        meta: dict[str, Any] = {
            "citations": citations,
            "session_id": session_id,
            "short_term_count": len(prompt_context.history),
            "short_term_original_count": len(history),
            "conversation_summary_chars": len(prompt_context.conversation_summary),
            "prompt_estimated_tokens": prompt_context.estimated_tokens,
            "dropped_history_count": prompt_context.dropped_history_count,
            "long_term_count": len(memories),
            "long_term_memory_ids": [m.id for m in memories],
            "memory_recall": _memory_recall_summary(memories),
            "memory_written_ids": [m.id for m in written],
        }

        meta["artifacts"] = [artifact.model_dump() for artifact in turn_result.artifacts]
        # 兼容旧客户端的单图字段, 完整报表列表通过 artifacts 提供。
        chart = next((a for a in reversed(turn_result.artifacts) if a.chart_data_uri), None)
        if chart:
            meta.update(chart_data_uri=chart.chart_data_uri, chart_kind=chart.chart_kind, table_row_count=chart.row_count)

        yield _sse("meta", meta)
        yield _sse("done", {})

    except Exception as e:
        logger.exception("SSE 流处理失败")
        yield _sse("error", {"message": _friendly_error_message(e)})


@router.post("/chat/stream", summary="问答（SSE 流式）")
async def chat_stream(req: ChatRequest, user: CurrentUserDep) -> EventSourceResponse:
    return EventSourceResponse(_stream_events(req, user))


@router.get("/sessions", response_model=list[SessionSummary], summary="会话列表")
async def list_sessions(
    user: CurrentUserDep,
    user_id: str = "default",
    limit: int = 30,
) -> list[SessionSummary]:
    store = get_conversation_store()
    target_user_id = _resolve_user_id(user_id, user)
    return [SessionSummary(**row) for row in store.list_sessions(user_id=target_user_id, limit=limit)]


@router.get("/sessions/{session_id}", response_model=SessionDetail, summary="会话详情")
async def get_session(
    session_id: str,
    user: CurrentUserDep,
    user_id: str = "default",
) -> SessionDetail:
    store = get_conversation_store()
    target_user_id = _resolve_user_id(user_id, user)
    sessions = [row for row in store.list_sessions(user_id=target_user_id, limit=500) if row["id"] == session_id]
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
async def delete_session(
    session_id: str,
    user: CurrentUserDep,
    user_id: str | None = None,
) -> dict[str, bool]:
    store = get_conversation_store()
    target_user_id = _resolve_user_id(user_id, user)
    sessions = [row for row in store.list_sessions(user_id=target_user_id, limit=500) if row["id"] == session_id]
    if not sessions:
        raise HTTPException(status_code=404, detail="session not found")
    deleted = store.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="session not found")
    return {"deleted": True}
