"""统一 Agent 运行入口, 预算耗尽时交付可识别的部分结果。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage
from langgraph.errors import GraphRecursionError
from langgraph.graph.message import add_messages

from ..core import get_settings
from ..core.budget import BudgetExceeded, RunBudget, budget_scope, current_budget, reserve_tool


def tool_error(exc: Exception) -> str:
    if isinstance(exc, BudgetExceeded):
        raise exc
    return "工具执行失败, 请检查参数或稍后重试。"


def guarded_tool(request, execute):
    reserve_tool(request.tool_call)
    return execute(request)


async def guarded_async_tool(request, execute):
    reserve_tool(request.tool_call)
    try:
        async with asyncio.timeout(get_settings().agent_tool_timeout_seconds):
            result = await execute(request)
        if budget := current_budget():
            budget.check()
        return result
    except TimeoutError as exc:
        if budget := current_budget():
            budget.stop("工具调用超时")
        raise BudgetExceeded("工具调用超时") from exc


def _merge(snapshot: dict, output: dict) -> dict:
    merged = {**snapshot, **output}
    if "messages" in output:
        merged["messages"] = add_messages(snapshot.get("messages", []), output["messages"])
    if "artifacts" in output:
        merged["artifacts"] = [*snapshot.get("artifacts", []), *output["artifacts"]]
    return merged


async def stream_graph_events(graph, state: dict) -> AsyncIterator[dict]:
    settings = get_settings()
    budget = RunBudget(
        settings.agent_model_call_limit,
        settings.agent_tool_call_limit,
        settings.agent_tool_repeat_limit,
        settings.agent_timeout_seconds,
    )
    snapshot = dict(state)
    with budget_scope(budget):
        try:
            async with asyncio.timeout(settings.agent_timeout_seconds):
                async for event in graph.astream_events(
                    state,
                    version="v2",
                    config={"recursion_limit": settings.agent_recursion_limit},
                ):
                    if event.get("event") == "on_chain_end":
                        output = event.get("data", {}).get("output")
                        parents = event.get("parent_ids", [])
                        if isinstance(output, dict):
                            if len(parents) == 1 and event.get("name") in {
                                "supervisor",
                                "qa",
                                "sql",
                                "general",
                                "tools",
                            }:
                                snapshot = _merge(snapshot, output)
                            elif not parents:
                                output = {**output, "usage": budget.usage(), "model_stats": budget.telemetry()}
                                event = {**event, "data": {**event["data"], "output": output}}
                    yield event
        except (BudgetExceeded, TimeoutError, GraphRecursionError) as exc:
            reason = budget.reason or (
                "本次任务执行超时"
                if isinstance(exc, TimeoutError)
                else "已达到图执行步数上限"
                if isinstance(exc, GraphRecursionError)
                else str(exc)
            )
            budget.stop(reason)
            tasks = [dict(task) for task in snapshot.get("tasks", [])]
            for task in tasks:
                if task["status"] in {"pending", "running"}:
                    task.update(status="blocked", summary=reason)
            snapshot = _merge(
                snapshot,
                {
                    "messages": [
                        AIMessage(
                            content=f"本次执行已停止: {reason}。已完成的结果保留, 剩余任务尚未完成。"
                        )
                    ],
                    "tasks": tasks,
                    "termination_reason": reason,
                    "next": "FINISH",
                    "usage": budget.usage(),
                    "model_stats": budget.telemetry(),
                },
            )
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "parent_ids": [],
                "data": {"output": snapshot},
            }


async def run_graph(graph, state: dict) -> dict:
    result = None
    async for event in stream_graph_events(graph, state):
        if event.get("event") == "on_chain_end" and not event.get("parent_ids"):
            result = event.get("data", {}).get("output")
    if not isinstance(result, dict):
        raise RuntimeError("未收到完整执行结果")
    return result
