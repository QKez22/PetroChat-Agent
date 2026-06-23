"""Supervisor 路由逻辑测试（离线：mock LLM）。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from petrochat.app.agent.nodes.supervisor_node import RouteDecision, supervisor_node


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


def test_supervisor_empty_question_falls_back() -> None:
    """空 question 不调 LLM，直接走 general 兜底。"""
    out = supervisor_node({"question": ""})
    assert out["next"] == "general"
    assert "兜底" in out["intent"] or "空" in out["intent"]


def test_route_decision_validates_choices() -> None:
    """next 只能是三选一。"""
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        RouteDecision(next="invalid_route", reasoning="x")
