"""LangGraph 全局状态对象。"""

from __future__ import annotations

from operator import add
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
    long_term_memories: list[dict[str, Any]]
    long_term_context: str
    retrieved: list[dict[str, Any]]
    answer: str
    citations: list[str]
    artifacts: Annotated[list[dict[str, Any]], add]
    sql_result: dict[str, Any]
    score: dict[str, Any]
    intent: str
    next: NextNode
    retry_count: int
    supervisor_step: int
    tasks: list[dict[str, Any]]
    requirements: list[dict[str, Any]]
    active_task_id: int
    termination_reason: str
    usage: dict[str, int]
    model_stats: list[dict[str, Any]]
