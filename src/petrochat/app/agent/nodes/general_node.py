"""General 节点 (ReAct 兜底) - 复合 / 不确定的问题走这里。

沿用 phase 2 的 ReAct 逻辑, 仍然保持工具循环:
  agent → tools? → agent ...
让 LLM 自由选用 5 个工具完成任务, 适用于:
  - 单位换算 (convert_unit)
  - 多工具协作 (先查知识再算)
  - supervisor 兜底 (intent 不明确)
"""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from loguru import logger

from ...core import AgentState, get_chat_llm, get_settings
from ...tools import ALL_TOOLS as LOCAL_TOOLS
from ..prompts import AGENT_SYSTEM_PROMPT


def _current_tools():
    s = get_settings()
    if s.mcp_enabled:
        from ...mcp import get_loaded_tools
        try:
            return get_loaded_tools()
        except Exception as exc:
            logger.warning("MCP 工具不可用，general 节点降级使用本地工具: {}", exc)
    return LOCAL_TOOLS


def general_node(state: AgentState) -> dict:
    """ReAct 兜底节点。"""
    messages = list(state.get("messages") or [])
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT), *messages]

    llm_with_tools = get_chat_llm().bind_tools(_current_tools())
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}
