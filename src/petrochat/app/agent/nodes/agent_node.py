"""ReAct agent 节点：LLM 自主决定是否调用工具。

工作流（被外层 graph 反复调用）：
  1. 拿到 state["messages"]（含 SystemMessage + HumanMessage + 历史 AIMessage/ToolMessage）
  2. LLM 看完上下文，要么返回最终答案，要么返回带 tool_calls 的 AIMessage
  3. 如果有 tool_calls，graph 的条件边会路由到 ToolNode 执行；否则 END
  4. ToolNode 执行完后回到本节点，本节点把工具结果连同历史一起再喂给 LLM

design 关键点：
  - bind_tools 必须在每次调用时生效（lru_cache LLM + tools 都是单例，没问题）
  - 不直接修改 state，只 return {"messages": [response]}，由 add_messages reducer 合并
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.messages import SystemMessage

from ...core import AgentState, get_chat_llm
from ...tools import ALL_TOOLS
from ..prompts import AGENT_SYSTEM_PROMPT


@lru_cache(maxsize=1)
def _llm_with_tools():
    """把 LLM 跟工具绑定。lru_cache 避免每次调用都重新构造。"""
    return get_chat_llm().bind_tools(ALL_TOOLS)


def agent_node(state: AgentState) -> dict:
    """ReAct agent 节点。"""
    messages = list(state.get("messages") or [])

    # 没有 SystemMessage 就前置一个（保证 agent 角色稳定）
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT)] + messages

    response = _llm_with_tools().invoke(messages)
    # 只返回新产生的 AIMessage；add_messages reducer 会自动 append 进 state["messages"]
    return {"messages": [response]}
