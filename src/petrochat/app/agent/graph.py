"""LangGraph StateGraph 装配。

第一阶段：单节点 graph，question → qa_node → END。
后续阶段在这里加 supervisor / tool_node / scoring_node 与条件边。
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from ..core import AgentState
from .nodes.qa_node import qa_node


@lru_cache(maxsize=1)
def build_graph():
    """构建并编译 StateGraph，返回可 invoke / stream 的 Runnable。

    第一阶段图形态：
        START → qa → END

    用 lru_cache 单例：graph 构建相对昂贵（含节点注册、edge 解析），
    应用生命周期内复用即可。
    """
    builder = StateGraph(AgentState)
    builder.add_node("qa", qa_node)
    builder.add_edge(START, "qa")
    builder.add_edge("qa", END)
    return builder.compile()
