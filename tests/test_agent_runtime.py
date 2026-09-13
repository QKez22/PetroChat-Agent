"""P1 调度及预算回归, 不调用外部模型或业务库。"""

from __future__ import annotations

import asyncio
import importlib
import time
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import ValidationError

from petrochat.app.agent import build_initial_state
from petrochat.app.agent.nodes.supervisor_node import RouteDecision
from petrochat.app.agent.result import build_turn_result
from petrochat.app.agent.runtime import run_graph
from petrochat.app.core import get_settings
from petrochat.app.core.budget import current_budget


@pytest.fixture
def harness(monkeypatch):
    graph_module = importlib.import_module("petrochat.app.agent.graph")
    supervisor_module = importlib.import_module("petrochat.app.agent.nodes.supervisor_node")
    env = SimpleNamespace(
        plan_calls=0, calls=[], tools=0, plan=[{"worker": "qa", "instruction": "解释规则"}]
    )

    def model_call():
        if budget := current_budget():
            budget.reserve("model")

    class Planner:
        def with_structured_output(self, *args, **kwargs):
            return self

        def invoke(self, messages):
            model_call()
            env.plan_calls += 1
            return RouteDecision(next=env.plan[0]["worker"], reasoning="计划", tasks=env.plan)

    def qa(state):
        model_call()
        env.calls.append(("qa", state["question"]))
        return {
            "messages": [AIMessage(content="规则证据 [1.2]。")],
            "retrieved": [{"content": "规则"}],
        }

    def sql(state):
        model_call()
        env.calls.append(("sql", state["question"]))
        return {"messages": [AIMessage(content="统计结果")], "sql_result": {"ok": True}}

    monkeypatch.setattr(supervisor_module, "get_chat_llm", Planner)
    monkeypatch.setattr(graph_module, "qa_node", qa)
    monkeypatch.setattr(graph_module, "sql_node", sql)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")

    async def run(question="原始复合问题"):
        graph_module.build_graph.cache_clear()
        return await run_graph(graph_module.build_graph(), build_initial_state(question))

    env.run = run
    env.graph = graph_module
    env.model_call = model_call
    return env


@pytest.mark.asyncio
async def test_simple_task_finishes_without_second_planner_call(harness):
    result = build_turn_result(await harness.run())
    assert harness.plan_calls == 1
    assert result.status == "completed"
    assert result.tasks[0]["status"] == "completed"
    assert result.usage == {"model_calls": 2, "tool_calls": 0}
    assert harness.calls == [("qa", "解释规则")]


@pytest.mark.asyncio
async def test_dependencies_receive_only_required_upstream_results(harness):
    harness.plan = [
        {"worker": "qa", "instruction": "解释规则"},
        {"worker": "sql", "instruction": "按规则统计", "depends_on": [1]},
    ]
    result = build_turn_result(await harness.run())
    assert result.status == "completed"
    assert harness.plan_calls == 1
    assert harness.calls[0] == ("qa", "解释规则")
    assert harness.calls[1][1].startswith("按规则统计")
    assert "规则证据" in harness.calls[1][1]
    assert "原始复合问题" not in harness.calls[1][1]
    assert "规则证据" in result.answer and "统计结果" in result.answer


@pytest.mark.asyncio
async def test_failed_dependency_is_blocked_but_independent_task_runs(harness, monkeypatch):
    harness.plan = [
        {"worker": "qa", "instruction": "查询缺失规则"},
        {"worker": "sql", "instruction": "按规则统计", "depends_on": [1]},
        {"worker": "sql", "instruction": "独立统计"},
    ]
    monkeypatch.setattr(
        harness.graph,
        "qa_node",
        lambda state: {"messages": [AIMessage(content="没有证据")], "retrieved": []},
    )
    result = build_turn_result(await harness.run())
    assert [t["status"] for t in result.tasks] == ["failed", "blocked", "completed"]
    assert harness.calls == [("sql", "独立统计")]
    assert result.status == "partial"
    assert "未完成" in result.answer


@pytest.mark.parametrize(
    "tasks",
    [
        [{"worker": "qa", "instruction": "same"}, {"worker": "qa", "instruction": " same "}],
        [{"worker": "qa", "instruction": "bad dependency", "depends_on": [1]}],
        [{"worker": "qa", "instruction": "bad dependency", "depends_on": [2]}],
        [{"worker": "qa", "instruction": "   "}],
    ],
)
def test_invalid_or_duplicate_plans_rejected(tasks):
    with pytest.raises(ValidationError):
        RouteDecision(next="qa", reasoning="plan", tasks=tasks)


@pytest.mark.asyncio
async def test_model_budget_preserves_completed_task(harness, monkeypatch):
    monkeypatch.setenv("AGENT_MODEL_CALL_LIMIT", "2")
    get_settings.cache_clear()
    harness.plan = [
        {"worker": "qa", "instruction": "解释规则"},
        {"worker": "sql", "instruction": "统计"},
    ]
    result = build_turn_result(await harness.run())
    assert result.status == "partial"
    assert [t["status"] for t in result.tasks] == ["completed", "blocked"]
    assert "规则证据" in result.answer and "上限" in result.answer
    assert result.usage["model_calls"] == 2
    assert harness.calls == [("qa", "解释规则")]


def looping_tools(harness, monkeypatch, *, slow=False, changing=False):
    @tool
    async def tick(value: int) -> str:
        """Test tool."""
        harness.tools += 1
        if slow:
            await asyncio.sleep(1)
        return "ok"

    def general(state):
        harness.model_call()
        count = sum(isinstance(m, ToolMessage) for m in state["messages"])
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "tick",
                            "id": f"tick-{count}",
                            "args": {"value": count if changing else 1},
                        }
                    ],
                )
            ]
        }

    harness.plan = [{"worker": "general", "instruction": "调用工具"}]
    monkeypatch.setattr(harness.graph, "_resolve_tools", lambda: [tick])
    monkeypatch.setattr(harness.graph, "general_node", general)


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", ["repeat", "tools", "recursion", "timeout"])
async def test_tool_loop_stops_before_extra_execution(harness, monkeypatch, limit):
    looping_tools(harness, monkeypatch, slow=limit == "timeout", changing=limit != "repeat")
    settings = {
        "repeat": ("AGENT_TOOL_REPEAT_LIMIT", "1"),
        "tools": ("AGENT_TOOL_CALL_LIMIT", "1"),
        "recursion": ("AGENT_RECURSION_LIMIT", "4"),
        "timeout": ("AGENT_TOOL_TIMEOUT_SECONDS", "0.05"),
    }
    monkeypatch.setenv(*settings[limit])
    get_settings.cache_clear()
    result = build_turn_result(await harness.run())
    assert result.status == "failed"
    assert result.termination_reason
    assert harness.tools == 1
    assert result.usage["tool_calls"] == 1


@pytest.mark.asyncio
async def test_deadline_prevents_late_thread_from_starting_model(harness, monkeypatch):
    monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", "0.05")
    get_settings.cache_clear()
    called = []

    def slow_worker(state):
        time.sleep(0.2)
        harness.model_call()
        called.append(True)
        return {"messages": [AIMessage(content="late")]}

    monkeypatch.setattr(harness.graph, "qa_node", slow_worker)
    result = build_turn_result(await harness.run())
    assert result.status == "failed" and "超时" in result.termination_reason
    await asyncio.sleep(0.3)
    assert called == []


@pytest.mark.asyncio
async def test_concurrent_requests_have_independent_budgets(harness, monkeypatch):
    monkeypatch.setenv("AGENT_MODEL_CALL_LIMIT", "2")
    get_settings.cache_clear()
    states = await asyncio.gather(harness.run("A"), harness.run("B"))
    assert all(build_turn_result(s).status == "completed" for s in states)
    assert all(s["usage"]["model_calls"] == 2 for s in states)


@pytest.mark.asyncio
async def test_general_only_receives_its_subquestion(harness, monkeypatch):
    harness.plan = [
        {"worker": "qa", "instruction": "解释规则"},
        {"worker": "general", "instruction": "换算 1 MPa"},
    ]
    captured = []

    def general(state):
        captured.extend(state["messages"])
        return {"messages": [AIMessage(content="换算结果")]}

    monkeypatch.setattr(harness.graph, "general_node", general)
    result = build_turn_result(await harness.run())
    assert result.status == "completed"
    assert [m.content for m in captured if isinstance(m, HumanMessage)] == ["换算 1 MPa"]
    assert not any(isinstance(m, AIMessage) for m in captured)
    assert "规则证据" in result.answer and "换算结果" in result.answer
