"""Supervisor 节点 —— 用 LLM 把用户问题分类到合适的子 agent。

设计：
  with_structured_output(method='function_calling') 强制返回 {next, reasoning}，
  方便审计 / LangSmith 看路由决策；不污染最终答案。
"""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from pydantic import BaseModel, Field

from ...core import AgentState, get_chat_llm

# 路由出口（与 state.NextNode 子集对齐，不重复定义以避免漂移）
Route = Literal["qa", "sql", "general"]


class RouteDecision(BaseModel):
    """Supervisor 的结构化输出。"""

    next: Route = Field(
        description=(
            "qa = 规范文档/概念/术语问答; "
            "sql = 业务数据查询/统计/清单 (事务/任务/部门等); "
            "general = 复合 / 单位换算 / 不属于前两类的兜底"
        )
    )
    reasoning: str = Field(description="一句话说明为什么选这个路由（中文）")


SUPERVISOR_PROMPT = """你是一个意图分类器，负责把用户问题路由到正确的子 agent。

【路由规则】
- qa：用户问的是规范文档里的概念、定义、术语、流程、解释。
  例：什么是 ITPM 策略？设备分级如何划分？
- sql：用户问的是业务数据查询、统计、清单（涉及"事务/任务/部门/设备/截止时间"等具体数据）。
  例：查仪表专业的事务清单；统计各部门数量；未来 3 天到期的事务
- general：纯计算（如单位换算）、不属于前两类、或需要多种工具配合的复合问题。
  例：1 MPa 等于多少 psi？查到 4.2.2 条款后再帮我算压力

【输出】
只输出路由决策，不要回答用户问题本身。
"""


def supervisor_node(state: AgentState) -> dict:
    """LLM 路由分类。返回 {'next': route, 'intent': reasoning}。"""
    question = state.get("question", "").strip()
    if not question:
        # 无问题不能 supervised；兜底走 general
        return {"next": "general", "intent": "空 question，走 general 兜底"}

    llm = get_chat_llm().with_structured_output(
        RouteDecision, method="function_calling"
    )
    decision: RouteDecision = llm.invoke([
        SystemMessage(content=SUPERVISOR_PROMPT),
        HumanMessage(content=question),
    ])
    logger.info("supervisor 路由: {} | {}", decision.next, decision.reasoning[:80])
    return {"next": decision.next, "intent": decision.reasoning}
