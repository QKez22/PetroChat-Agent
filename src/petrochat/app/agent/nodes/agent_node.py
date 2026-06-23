"""ReAct agent 节点 —— Phase 3: 工具源可切换 (local / MCP)。"""

from __future__ import annotations

from langchain_core.messages import SystemMessage

from ...core import AgentState, get_chat_llm, get_settings
from ...tools import ALL_TOOLS as LOCAL_TOOLS
from ..prompts import AGENT_SYSTEM_PROMPT


def _current_tools():
    s = get_settings()
    if s.mcp_enabled:
        from ...mcp import get_loaded_tools
        return get_loaded_tools()
    return LOCAL_TOOLS


def agent_node(state: AgentState) -> dict:
    messages = list(state.get("messages") or [])
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT)] + messages

    llm_with_tools = get_chat_llm().bind_tools(_current_tools())
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}
