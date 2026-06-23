"""LangGraph 装配测试（Phase 4: Supervisor 模式）。"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from petrochat.app.agent import build_graph, build_initial_state


def test_graph_builds() -> None:
    assert build_graph() is not None


def test_graph_has_all_phase4_nodes() -> None:
    g = build_graph()
    for n in ("supervisor", "qa", "sql", "general", "tools"):
        assert n in g.nodes, f"缺节点 {n}"


def test_graph_runnable_interface() -> None:
    g = build_graph()
    assert hasattr(g, "invoke")
    assert hasattr(g, "stream")
    assert hasattr(g, "astream")


def test_initial_state_shape() -> None:
    s = build_initial_state("hello")
    msgs = s["messages"]
    assert len(msgs) == 2
    assert isinstance(msgs[0], SystemMessage)
    assert isinstance(msgs[1], HumanMessage)
    assert msgs[1].content == "hello"
    assert s["question"] == "hello"
