"""Supervisor 路由逻辑测试（离线：mock LLM）。"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from petrochat.app.agent.nodes.supervisor_node import RouteDecision, supervisor_node


@pytest.fixture(autouse=True)
def mock_plan_review(monkeypatch):
    # 本文件测试路由；独立审核拒绝路径由语义契约测试覆盖。
    monkeypatch.setattr("petrochat.app.agent.nodes.supervisor_node.review_plan", lambda *args: [])


@pytest.mark.parametrize("route", ["qa", "sql", "general"])
def test_supervisor_returns_state_update(route: str) -> None:
    """supervisor_node 返回 dict 含 next & intent 字段。"""
    fake_decision = RouteDecision(next=route, reasoning="测试路由")

    class _FakeLLM:
        def invoke(self, _msgs):
            return fake_decision

    class _FakeChat:
        def with_structured_output(self, *args, **kwargs):
            return _FakeLLM()

    with patch(
        "petrochat.app.agent.nodes.supervisor_node.get_chat_llm",
        return_value=_FakeChat(),
    ):
        out = supervisor_node({"question": "测试问题"})

    assert out["next"] == route
    assert "测试" in out["intent"]


def test_supervisor_can_finish() -> None:
    """supervisor 可以决策 FINISH 结束循环。"""
    fake_decision = RouteDecision(next="FINISH", reasoning="已完整回答")

    class _FakeLLM:
        def invoke(self, _msgs):
            return fake_decision

    class _FakeChat:
        def with_structured_output(self, *args, **kwargs):
            return _FakeLLM()

    with patch(
        "petrochat.app.agent.nodes.supervisor_node.get_chat_llm",
        return_value=_FakeChat(),
    ):
        out = supervisor_node(
            {"question": "测试", "messages": [HumanMessage("测试"), AIMessage("已回答")]}
        )

    assert out["next"] == "FINISH"
    assert out["supervisor_step"] == 1


def test_supervisor_increments_step() -> None:
    """每次决策 supervisor_step 自增 1。"""
    fake_decision = RouteDecision(next="FINISH", reasoning="结束")

    class _FakeLLM:
        def invoke(self, _msgs):
            return fake_decision

    class _FakeChat:
        def with_structured_output(self, *args, **kwargs):
            return _FakeLLM()

    with patch(
        "petrochat.app.agent.nodes.supervisor_node.get_chat_llm",
        return_value=_FakeChat(),
    ):
        out = supervisor_node({"question": "测试", "supervisor_step": 2})

    assert out["supervisor_step"] == 3


def test_supervisor_cannot_finish_before_answering() -> None:
    class Planner:
        def with_structured_output(self, *args, **kwargs):
            return self

        def invoke(self, messages):
            return RouteDecision(next="FINISH", reasoning="过早结束")

    with patch("petrochat.app.agent.nodes.supervisor_node.get_chat_llm", return_value=Planner()):
        out = supervisor_node(
            {
                "question": "新问题",
                "messages": [HumanMessage("旧问题"), AIMessage("旧回答"), HumanMessage("新问题")],
            }
        )
    assert out["next"] == "general"
    assert out["tasks"][0]["instruction"] == "新问题"


def test_supervisor_max_steps_force_finish() -> None:
    """达到 SUPERVISOR_MAX_STEPS 时强制 FINISH，不调 LLM。"""
    from petrochat.app.agent.nodes.supervisor_node import SUPERVISOR_MAX_STEPS

    llm_called = False

    class _FakeLLM:
        def invoke(self, _msgs):
            nonlocal llm_called
            llm_called = True
            raise AssertionError("达到最大步数不应调用 LLM")

    class _FakeChat:
        def with_structured_output(self, *args, **kwargs):
            return _FakeLLM()

    with patch(
        "petrochat.app.agent.nodes.supervisor_node.get_chat_llm",
        return_value=_FakeChat(),
    ):
        out = supervisor_node(
            {
                "question": "测试",
                "supervisor_step": SUPERVISOR_MAX_STEPS,
            }
        )

    assert out["next"] == "FINISH"
    assert not llm_called
    assert "最大步数" in out["intent"] or "强制" in out["intent"]


def test_supervisor_passes_worker_outputs_to_llm() -> None:
    """supervisor 把 worker 的 AIMessage 产出传给 LLM 做下一轮决策。"""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    captured: dict = {}

    fake_decision = RouteDecision(next="FINISH", reasoning="worker 已完成")

    class _FakeLLM:
        def invoke(self, msgs):
            captured["msgs"] = list(msgs)
            return fake_decision

    class _FakeChat:
        def with_structured_output(self, *args, **kwargs):
            return _FakeLLM()

    worker_output = AIMessage(content="仪表专业共 5 条事务")
    with (
        patch(
            "petrochat.app.agent.nodes.supervisor_node.get_chat_llm",
            return_value=_FakeChat(),
        ),
        pytest.raises(ValueError, match="计划覆盖校验"),
    ):
        supervisor_node(
            {
                "question": "查仪表事务并统计数量",
                "messages": [
                    SystemMessage(content="业务系统 prompt"),
                    HumanMessage(content="查仪表事务并统计数量"),
                    worker_output,
                ],
                "supervisor_step": 1,
            }
        )

    msgs = captured["msgs"]
    # 第 0 条应被替换为 supervisor 自己的 system prompt
    assert msgs[0].content != "业务系统 prompt"
    # worker 产出应保留在传给 LLM 的 messages 里（这是循环决策的关键）
    assert any(m is worker_output for m in msgs)


def test_supervisor_empty_question_falls_back() -> None:
    """空 question 不调 LLM，直接走 general 兜底。"""
    out = supervisor_node({"question": ""})
    assert out["next"] == "general"
    assert "兜底" in out["intent"] or "空" in out["intent"]


def test_route_decision_validates_choices() -> None:
    """next 只能是 qa/sql/general/FINISH 四选一。"""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        RouteDecision(next="invalid_route", reasoning="x")
