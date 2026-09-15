"""LangGraph StateGraph 装配 —— Phase 4: Supervisor + 三路子 agent。"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from loguru import logger

from ..core import AgentState, get_settings
from ..memory import build_conversation_summary_message, build_memory_system_message
from ..tools import ALL_TOOLS as LOCAL_TOOLS
from ..tools.report_page import read_report_page
from .nodes.general_node import general_node
from .nodes.qa_node import qa_node
from .nodes.sql_node import sql_node
from .nodes.supervisor_node import supervisor_node
from .prompts import AGENT_SYSTEM_PROMPT
from .runtime import guarded_async_tool, guarded_tool, tool_error
from .tasks import wrap_worker


def _resolve_tools():
    s = get_settings()
    if s.mcp_enabled:
        from ..mcp import get_loaded_tools

        try:
            tools = get_loaded_tools()
            logger.info("graph 使用 MCP 工具: {} 个", len(tools))
            return [*tools, read_report_page]
        except Exception as exc:
            logger.warning("MCP 工具不可用，graph 降级使用本地工具: {}", exc)
    logger.info("graph 使用本地工具: {} 个", len(LOCAL_TOOLS))
    return LOCAL_TOOLS


def _route_after_supervisor(state: AgentState) -> str:
    nxt = state.get("next", "FINISH")
    if nxt == "FINISH":
        return END
    if nxt not in {"qa", "sql", "general"}:
        return "general"
    return nxt


def _route_after_general(state: AgentState) -> str:
    """general 执行后：有 tool_calls 去 tools，否则回 supervisor 评估是否结束。"""
    messages = state.get("messages") or []
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            if getattr(msg, "tool_calls", None):
                return "tools"
            return "supervisor"
    return "supervisor"


@lru_cache(maxsize=1)
def build_graph():
    """构建并编译 Supervisor + 三路子 agent StateGraph。"""
    tools = _resolve_tools()

    builder = StateGraph(AgentState)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("qa", wrap_worker("qa", qa_node))
    builder.add_node("sql", wrap_worker("sql", sql_node))
    builder.add_node("general", wrap_worker("general", general_node))
    builder.add_node(
        "tools",
        ToolNode(
            tools,
            wrap_tool_call=guarded_tool,
            awrap_tool_call=guarded_async_tool,
            handle_tool_errors=tool_error,
        ),
    )

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        {"qa": "qa", "sql": "sql", "general": "general", END: END},
    )
    # worker 执行完回 supervisor（而非直接 END），让 supervisor 评估是否还需要继续分派
    builder.add_edge("qa", "supervisor")
    builder.add_edge("sql", "supervisor")
    builder.add_conditional_edges(
        "general",
        _route_after_general,
        {"tools": "tools", "supervisor": "supervisor"},
    )
    builder.add_edge("tools", "general")
    return builder.compile()


def build_initial_state(
    question: str,
    *,
    session_id: str | None = None,
    user_id: str = "default",
    history: list[dict] | None = None,
    long_term_memories: list[dict] | None = None,
    long_term_context: str = "",
    conversation_summary: str = "",
) -> dict:
    history = history or []
    long_term_memories = long_term_memories or []
    messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT)]
    memory_msg = build_memory_system_message(long_term_context)
    if memory_msg:
        messages.append(memory_msg)
    summary_text = build_conversation_summary_message(conversation_summary)
    if summary_text:
        messages.append(SystemMessage(content=summary_text))
    for item in history:
        role = item.get("role")
        content = item.get("content") or ""
        if not content:
            continue
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            status = item.get("status", "unknown")
            prefix = f"[历史任务状态: {status}; 不能视为全部完成]\n" if status in {"partial", "failed"} else ""
            messages.append(AIMessage(content=prefix + content))
    messages.append(HumanMessage(content=question))
    sql_history = history
    if conversation_summary.startswith("【当前用户约束") and "[END_CONSTRAINTS]" in conversation_summary:
        # SQL 只继承当前约束快照, 避免 hints 将已失效的历史部门值重新并入筛选。
        sql_history = [{"role": "user", "content": conversation_summary.split("[END_CONSTRAINTS]", 1)[0]}]
    return {
        "question": question,
        "session_id": session_id or "",
        "user_id": user_id,
        "short_term_messages": sql_history,
        "conversation_summary": conversation_summary,
        "long_term_memories": long_term_memories,
        "long_term_context": long_term_context,
        "messages": messages,
    }
