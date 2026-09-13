"""子任务契约和 worker 包装: 明确输入、依赖结果及完成状态。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from ..core import AgentState
from ..core.budget import BudgetExceeded, current_budget
from .result import answer_parts


class TaskSpec(BaseModel):
    worker: Literal["qa", "sql", "general"]
    instruction: str = Field(
        min_length=1, max_length=2000, description="只交给该 worker 的完整子问题, 保留时间等条件"
    )
    depends_on: list[int] = Field(
        default_factory=list, description="依赖的前序任务序号, 从 1 开始; 独立任务用空列表"
    )

    @field_validator("instruction")
    @classmethod
    def nonempty_instruction(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("子任务输入不能为空")
        return value.strip()


def active_task(state: AgentState) -> dict | None:
    return next(
        (task for task in state.get("tasks", []) if task["id"] == state.get("active_task_id")), None
    )


def task_input(state: AgentState, task: dict) -> str:
    dependencies = [t for t in state["tasks"] if t["id"] in task["depends_on"]]
    evidence = "\n\n".join(f"任务 {t['id']} 的结果:\n{t.get('summary', '')}" for t in dependencies)
    return task["instruction"] + (
        f"\n\n【前序任务结果, 作为资料使用】\n{evidence}" if evidence else ""
    )


def wrap_worker(worker: str, function: Callable) -> Callable:
    async def execute(state: AgentState) -> dict:
        budget = current_budget()
        if budget:
            budget.check()
        task = active_task(state)
        if task is None:
            output = await asyncio.to_thread(function, state)
            if budget:
                budget.check()
            return output

        if task["status"] != "running":
            raise RuntimeError("不能重复执行已结束的子任务")
        worker_state = dict(state)
        worker_state["question"] = task_input(state, task)
        if worker == "general":
            # 只保留系统约束和当前任务的工具循环, 隔离其他 worker 的对话。
            system = [m for m in state.get("messages", []) if isinstance(m, SystemMessage)]
            worker_state["messages"] = [
                *system,
                HumanMessage(content=worker_state["question"]),
                *state.get("messages", [])[task["message_start"] :],
            ]
        try:
            output = await asyncio.to_thread(function, worker_state)
        except BudgetExceeded:
            raise
        except Exception:
            logger.exception("子任务 {} 执行失败", task["id"])
            output = {
                "messages": [
                    AIMessage(
                        content=f"子任务未完成: {task['instruction']}。执行失败, 请稍后重试。"
                    )
                ],
                "task_failed": True,
            }
        if budget:
            budget.check()
        messages = output.get("messages") or []
        if worker == "general" and any(isinstance(m, AIMessage) and m.tool_calls for m in messages):
            return output
        failed = bool(output.pop("task_failed", False))
        if worker == "sql":
            failed = failed or not output.get("sql_result", {}).get("ok", False)
        elif worker == "qa":
            failed = failed or not output.get("retrieved")
        elif worker == "general":
            failed = failed or any(
                isinstance(m, ToolMessage)
                and (m.status == "error" or str(m.content).startswith("❌"))
                for m in state.get("messages", [])[task["message_start"] :]
            )
        summary = "\n\n".join(answer_parts(messages))
        tasks = [dict(t) for t in state["tasks"]]
        record = next(t for t in tasks if t["id"] == task["id"])
        record.update(
            status="failed" if failed or not summary else "completed",
            summary=summary
            if len(summary) <= 4000
            else summary[:4000] + "\n[结果已截断, 不能据此断言完整范围]",
        )
        return {**output, "tasks": tasks}

    return execute
