"""LangGraph 装配测试（Phase 4: Supervisor 模式）。"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

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


def test_initial_state_includes_short_term_history() -> None:
    s = build_initial_state(
        "继续",
        session_id="s1",
        user_id="u1",
        history=[
            {"role": "user", "content": "上一问"},
            {"role": "assistant", "content": "上一答"},
        ],
    )
    msgs = s["messages"]
    assert len(msgs) == 4
    assert isinstance(msgs[1], HumanMessage)
    assert isinstance(msgs[2], AIMessage)
    assert msgs[1].content == "上一问"
    assert msgs[2].content == "上一答"
    assert msgs[3].content == "继续"
    assert s["session_id"] == "s1"
    assert s["user_id"] == "u1"
    assert len(s["short_term_messages"]) == 2
