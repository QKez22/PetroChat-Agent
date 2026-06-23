"""LangGraph StateGraph 装配 —— Phase 4: Supervisor + 三路子 agent。"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from loguru import logger

from ..core import AgentState, get_settings
from ..tools import ALL_TOOLS as LOCAL_TOOLS
from .nodes.general_node import general_node
from .nodes.qa_node import qa_node
from .nodes.sql_node import sql_node
from .nodes.supervisor_node import supervisor_node
from .prompts import AGENT_SYSTEM_PROMPT


def _resolve_tools():
    s = get_settings()
    if s.mcp_enabled:
        from ..mcp import get_loaded_tools
        tools = get_loaded_tools()
        logger.info("graph 使用 MCP 工具: {} 个", len(tools))
        return tools
    logger.info("graph 使用本地工具: {} 个", len(LOCAL_TOOLS))
    return LOCAL_TOOLS


def _route_after_supervisor(state: AgentState) -> str:
    nxt = state.get("next", "general")
    if nxt not in {"qa", "sql", "general"}:
        return "general"
    return nxt


@lru_cache(maxsize=1)
def build_graph():
    """构建并编译 Supervisor + 三路子 agent StateGraph。"""
    tools = _resolve_tools()

    builder = StateGraph(AgentState)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("qa", qa_node)
    builder.add_node("sql", sql_node)
    builder.add_node("general", general_node)
    builder.add_node("tools", ToolNode(tools))

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        {"qa": "qa", "sql": "sql", "general": "general"},
    )
    builder.add_edge("qa", END)
    builder.add_edge("sql", END)
    builder.add_conditional_edges("general", tools_condition)
    builder.add_edge("tools", "general")
    return builder.compile()


def build_initial_state(question: str) -> dict:
    return {
        "question": question,
        "messages": [
            SystemMessage(content=AGENT_SYSTEM_PROMPT),
            HumanMessage(content=question),
        ],
    }
