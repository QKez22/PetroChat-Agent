"""LangGraph StateGraph 装配 —— Phase 2: ReAct 模式。

图形态：
    START → agent ──┬─→ tools → agent  (循环：LLM 要调工具时)
                    └─→ END             (LLM 给出最终答案时)
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from ..core import AgentState
from ..tools import ALL_TOOLS
from .nodes.agent_node import agent_node
from .prompts import AGENT_SYSTEM_PROMPT


@lru_cache(maxsize=1)
def build_graph():
    """构建并编译 ReAct StateGraph。"""
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(ALL_TOOLS))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile()


def build_initial_state(question: str) -> dict:
    """从一个问题构造图的初始 state。"""
    return {
        "question": question,
        "messages": [
            SystemMessage(content=AGENT_SYSTEM_PROMPT),
            HumanMessage(content=question),
        ],
    }
