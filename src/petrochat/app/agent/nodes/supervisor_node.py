"""Supervisor 节点 —— 可循环的任务协调者。

设计：
  - 首轮 function_calling 返回子任务、输入和前序依赖；
  - worker 返回后依据完成记录继续分派，避免重复询问模型是否结束；
  - 失败依赖阻断下游，独立任务仍可执行；最多分派 5 个任务。
"""

from __future__ import annotations

import re
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from loguru import logger
from pydantic import BaseModel, Field, model_validator

from ...core import AgentState, get_chat_llm
from ..requirements import extract_requirements, plan_coverage, review_plan
from ..result import answer_parts
from ..tasks import TaskSpec

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
            "general = 单位换算 / 通用工具 / 不属于前两类的兜底; "
            "FINISH = 用户问题已被完整回答，结束本轮协调"
        )
    )
    reasoning: str = Field(description="一句话说明为什么这样决策（中文）")

    tasks: list[TaskSpec] = Field(
        default_factory=list,
        max_length=5,
        description="首轮拆分全部任务, 按执行顺序排列; 简单问题只有一个任务",
    )

    @model_validator(mode="after")
    def validate_plan(self):
        seen = set()
        for index, task in enumerate(self.tasks, 1):
            key = (task.worker, "".join(task.instruction.split()).casefold())
            if key in seen:
                raise ValueError("不能重复分派相同子任务")
            seen.add(key)
            if any(dep < 1 or dep >= index for dep in task.depends_on):
                raise ValueError("子任务只能依赖前序任务")
        return self


SUPERVISOR_PROMPT = """你是任务协调者，负责把用户问题分派给合适的子 agent，并在子任务完成后决定是否结束。

【子 agent】
- qa：规范文档/概念/术语/流程/解释问答。例：什么是 ITPM 策略？设备分级如何划分？
- sql：业务数据查询/统计/清单及对应表格图表。一个 sql 任务自动生成报表, 不另设绘图任务。
- general：纯计算（单位换算）、通用工具、不属于前两类的兜底。例：1 MPa 等于多少 psi？

【决策规则】
1. 首轮生成 tasks, 拆出用户要求的全部子任务。简单问题只安排一个任务。
2. 每个任务包含 worker、instruction、depends_on。instruction 是该 worker 的完整子问题,
   必须保留时间、部门、筛选条件, 将历史对话中的指代展开。不要将原始复合整题交给每个 worker。
3. depends_on 是前序任务序号列表(从 1 开始)。只有确实需要上游结果时才填写。
   例如“解释 ITPM 并统计事务”是独立任务; “按刚查出的规则筛选数据”则依赖规则查询。
4. 不安排重复任务, 不添加用户没有要求的工作。最多 5 个任务。
5. next 指向首个任务的 worker。已有答案且无需任何任务时才允许 FINISH。
6. 后续由程序根据任务完成记录继续分派和结束, 不需要计划额外的“总结”任务。

【输出】
输出 {next, reasoning, tasks}。仅使用 function_calling 返回结构化结果。
"""


def _dispatch(state: AgentState, tasks: list[dict], step: int) -> dict:
    tasks = [dict(task) for task in tasks]
    for task in tasks:
        if task["status"] != "pending":
            continue
        dependencies = [t for t in tasks if t["id"] in task["depends_on"]]
        if any(t["status"] in {"failed", "blocked"} for t in dependencies):
            task.update(status="blocked", summary="前序任务未完成, 无法执行")
            continue
        if not all(t["status"] == "completed" for t in dependencies):
            continue
        if step >= SUPERVISOR_MAX_STEPS:
            task.update(status="blocked", summary="达到协调步数上限")
            continue
        task.update(status="running", message_start=len(state.get("messages", [])))
        return {
            "tasks": tasks,
            "active_task_id": task["id"],
            "next": task["worker"],
            "intent": f"执行任务 {task['id']}: {task['instruction']}",
            "supervisor_step": step + 1,
        }
    failed = [t for t in tasks if t["status"] != "completed"]
    update = {
        "tasks": tasks,
        "active_task_id": 0,
        "next": "FINISH",
        "supervisor_step": step,
        "intent": "任务执行结束",
    }
    if failed:
        update["messages"] = [
            AIMessage(
                content="以下子任务未完成：\n"
                + "\n".join(
                    f"- {t['instruction']}（{'执行失败' if t['status'] == 'failed' else '未执行'}）"
                    for t in failed
                )
            )
        ]
    return update


def supervisor_node(state: AgentState) -> dict:
    """循环任务协调。返回 {'next': action, 'intent': reasoning, 'supervisor_step': n}。"""
    step = int(state.get("supervisor_step") or 0)
    if state.get("tasks"):
        return _dispatch(state, state["tasks"], step)

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
            "supervisor_step": step + 1,
        }

    # 3) 构造 supervisor 输入：用自己的 system prompt 替换业务 system prompt，
    #    保留 memory/summary/history/question/worker 产出，让 supervisor 能看到进度。
    messages = list(state.get("messages") or [])
    if messages and isinstance(messages[0], SystemMessage):
        messages[0] = SystemMessage(content=SUPERVISOR_PROMPT)
    else:
        messages = [SystemMessage(content=SUPERVISOR_PROMPT), *messages]

    llm = get_chat_llm().with_structured_output(RouteDecision, method="function_calling")
    requirements = extract_requirements(question)
    decision: RouteDecision = llm.invoke(messages)
    if not requirements and len(decision.tasks) == 1 and decision.tasks[0].worker == "sql":
        from ...sql.contract import extract_contract

        requirements = [
            {
                "id": 1,
                "worker": "sql",
                "source": question,
                "start": 0,
                "end": len(question),
                "contract": extract_contract(question),
            }
        ]
    needs_review = (
        len(requirements) > 1
        or len(decision.tasks) > 1
        or any(t.worker == "sql" for t in decision.tasks)
        or bool(re.search(r"[，；]|并|然后|以及|再", question))
    )
    errors, assigned = plan_coverage(requirements, decision.tasks)
    if not errors and needs_review:
        errors = review_plan(question, decision.tasks, state.get("short_term_messages"))
    if errors:
        decision = llm.invoke(
            [
                *messages,
                HumanMessage(
                    content=(
                        "计划未覆盖原始需求，请修复全部 tasks，保留每项原文中的条件。\n"
                        + "\n".join(errors)
                        + "\n原始问题："
                        + question
                    )
                ),
            ]
        )
        errors, assigned = plan_coverage(requirements, decision.tasks)
        if not errors and needs_review:
            errors = review_plan(question, decision.tasks, state.get("short_term_messages"))
        if errors:
            raise ValueError("计划覆盖校验未通过：" + "；".join(errors))
    specs = decision.tasks
    if not specs and (decision.next != "FINISH" or not answer_parts(messages)):
        worker = decision.next if decision.next != "FINISH" else "general"
        specs = [TaskSpec(worker=worker, instruction=question)]
    if specs:
        tasks = [
            {
                "id": i,
                **spec.model_dump(),
                "status": "pending",
                "summary": "",
                "requirements": assigned.get(i - 1, []),
            }
            for i, spec in enumerate(specs, 1)
        ]
        update = _dispatch(state, tasks, step)
        update["requirements"] = requirements
        update["intent"] = decision.reasoning
        return update
    logger.info(
        "supervisor 决策 (step {}): {} | {}",
        step + 1,
        decision.next,
        decision.reasoning[:80],
    )
    return {
        "next": decision.next,
        "intent": decision.reasoning,
        "supervisor_step": step + 1,
    }
