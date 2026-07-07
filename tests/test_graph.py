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


def test_initial_state_includes_long_term_memory_context() -> None:
    s = build_initial_state(
        "统计事务",
        user_id="1",
        long_term_memories=[{"id": "101", "content": "默认看炼油一部"}],
        long_term_context="1. [memory:101] 默认看炼油一部",
    )
    msgs = s["messages"]
    assert len(msgs) == 3
    assert isinstance(msgs[0], SystemMessage)
    assert isinstance(msgs[1], SystemMessage)
    assert isinstance(msgs[2], HumanMessage)
    assert "用户长期记忆" in str(msgs[1].content)
    assert s["long_term_memories"][0]["id"] == "101"
    assert s["long_term_context"]


def test_initial_state_includes_conversation_summary_before_recent_history() -> None:
    s = build_initial_state(
        "continue",
        conversation_summary="- 已确认条件: refinery-one active tasks",
        history=[
            {"role": "user", "content": "recent question"},
            {"role": "assistant", "content": "recent answer"},
        ],
    )
    msgs = s["messages"]
    assert len(msgs) == 5
    assert isinstance(msgs[1], SystemMessage)
    assert "会话滚动摘要" in str(msgs[1].content)
    assert isinstance(msgs[2], HumanMessage)
    assert msgs[2].content == "recent question"
    assert s["conversation_summary"]
