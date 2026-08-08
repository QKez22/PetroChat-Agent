"""Supervisor 节点 —— 可循环的任务协调者。

设计：
  - with_structured_output(method='function_calling') 强制返回 {next, reasoning}；
  - next ∈ {qa, sql, general, FINISH}：前三个分派子 agent，FINISH 结束循环；
  - 每次 worker 执行完回到 supervisor，supervisor 看 messages 历史（含 worker 产出）
    决定「继续分派下一个 / 结束」；
  - SUPERVISOR_MAX_STEPS 兜底防死循环；supervisor_step 每轮自增。
"""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import SystemMessage
from loguru import logger
from pydantic import BaseModel, Field

from ...core import AgentState, get_chat_llm

# 循环上限：超过即强制 FINISH，防止 supervisor 反复分派导致死循环。
# 多数任务 2-3 步完成，5 是安全垫。
SUPERVISOR_MAX_STEPS = 5

Action = Literal["qa", "sql", "general", "FINISH"]


class RouteDecision(BaseModel):
    """Supervisor 的结构化输出。"""

    next: Action = Field(
        description=(
            "qa = 规范文档/概念/术语问答; "
            "sql = 业务数据查询/统计/清单 (事务/任务/部门等); "
            "general = 复合 / 单位换算 / 不属于前两类的兜底; "
            "FINISH = 用户问题已被完整回答，结束本轮协调"
        )
    )
    reasoning: str = Field(description="一句话说明为什么这样决策（中文）")


SUPERVISOR_PROMPT = """你是任务协调者，负责把用户问题分派给合适的子 agent，并在子任务完成后决定是否结束。

【子 agent】
- qa：规范文档/概念/术语/流程/解释问答。例：什么是 ITPM 策略？设备分级如何划分？
- sql：业务数据查询/统计/清单（事务/任务/部门/设备/截止时间等）。例：查仪表专业的事务清单；统计各部门数量。
- general：纯计算（单位换算）、复合问题、不属于前两类的兜底。例：1 MPa 等于多少 psi？

【决策规则】
1. 如果当前还没有任何子 agent 的产出（这是第一轮），根据问题类型分派一个子 agent。
2. 如果已有子 agent 产出，判断用户问题是否已完整回答：
   - 已完整回答 → 输出 FINISH
   - 还残留未完成的子任务（典型：多意图问题只做了一半，比如「先讲策略再统计」才做完前半截）→ 分派下一个需要的子 agent
3. 不要重复分派已经完成相同工作的子 agent。
4. 如果不确定还需不需要继续，倾向 FINISH（避免无意义循环）。

【输出】
只输出 {next, reasoning}。next ∈ {qa, sql, general, FINISH}。
reasoning 用一句话中文说明。
"""


def supervisor_node(state: AgentState) -> dict:
    """循环任务协调。返回 {'next': action, 'intent': reasoning, 'supervisor_step': n}。"""
    step = int(state.get("supervisor_step") or 0)

    # 1) 死循环保护：超过最大步数强制结束
    if step >= SUPERVISOR_MAX_STEPS:
        logger.warning("supervisor 达到最大步数 {}，强制 FINISH", SUPERVISOR_MAX_STEPS)
        return {
            "next": "FINISH",
            "intent": f"达到最大步数 {SUPERVISOR_MAX_STEPS}，强制结束",
            "supervisor_step": step,
        }

    # 2) 空问题兜底
    question = (state.get("question") or "").strip()
    if not question:
        return {
            "next": "general",
            "intent": "空 question，走 general 兜底",
            "supervisor_step": step,
        }

    # 3) 构造 supervisor 输入：用自己的 system prompt 替换业务 system prompt，
    #    保留 memory/summary/history/question/worker 产出，让 supervisor 能看到进度。
    messages = list(state.get("messages") or [])
    if messages and isinstance(messages[0], SystemMessage):
        messages[0] = SystemMessage(content=SUPERVISOR_PROMPT)
    else:
        messages = [SystemMessage(content=SUPERVISOR_PROMPT), *messages]

    llm = get_chat_llm().with_structured_output(
        RouteDecision, method="function_calling"
    )
    decision: RouteDecision = llm.invoke(messages)
    logger.info(
        "supervisor 决策 (step {}): {} | {}",
        step + 1, decision.next, decision.reasoning[:80],
    )
    return {
        "next": decision.next,
        "intent": decision.reasoning,
        "supervisor_step": step + 1,
    }
