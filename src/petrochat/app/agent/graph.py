"""LangGraph StateGraph 装配 —— Phase 3: 工具源可切换 (local / MCP)。"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from loguru import logger

from ..core import AgentState, get_settings
from ..tools import ALL_TOOLS as LOCAL_TOOLS
from .nodes.agent_node import agent_node
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


@lru_cache(maxsize=1)
def build_graph():
    tools = _resolve_tools()
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile()


def build_initial_state(question: str) -> dict:
    return {
        "question": question,
        "messages": [
            SystemMessage(content=AGENT_SYSTEM_PROMPT),
            HumanMessage(content=question),
        ],
    }
