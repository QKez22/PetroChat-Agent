"""LangGraph 装配测试（Phase 2: ReAct）。"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from petrochat.app.agent import build_graph, build_initial_state


def test_graph_builds() -> None:
    graph = build_graph()
    assert graph is not None


def test_graph_has_agent_and_tools_nodes() -> None:
    graph = build_graph()
    assert "agent" in graph.nodes
    assert "tools" in graph.nodes


def test_graph_runnable_interface() -> None:
    graph = build_graph()
    assert hasattr(graph, "invoke")
    assert hasattr(graph, "stream")
    assert hasattr(graph, "astream")


def test_initial_state_shape() -> None:
    s = build_initial_state("hello")
    msgs = s["messages"]
    assert len(msgs) == 2
    assert isinstance(msgs[0], SystemMessage)
    assert isinstance(msgs[1], HumanMessage)
    assert msgs[1].content == "hello"
    assert s["question"] == "hello"
