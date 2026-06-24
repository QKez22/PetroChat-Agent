"""LangGraph 全局状态对象。"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

NextNode = Literal["qa", "sql", "general", "tool", "scoring", "FINISH"]


class AgentState(TypedDict, total=False):
    """LangGraph 节点间共享的状态对象。"""

    question: str
    session_id: str
    user_id: str
    messages: Annotated[list[BaseMessage], add_messages]
    short_term_messages: list[dict[str, Any]]
    conversation_summary: str
    retrieved: list[dict[str, Any]]
    answer: str
    citations: list[str]
    score: dict[str, Any]
    intent: str
    next: NextNode
    retry_count: int
