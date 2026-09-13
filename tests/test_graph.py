"""LangGraph 装配测试（循环 Supervisor 模式）。"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END

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


# ===== 循环 Supervisor：路由函数纯逻辑 =====


def test_route_after_supervisor_dispatches_workers() -> None:
    """supervisor 决策 qa/sql/general 时路由到对应 worker。"""
    from petrochat.app.agent.graph import _route_after_supervisor

    assert _route_after_supervisor({"next": "qa"}) == "qa"
    assert _route_after_supervisor({"next": "sql"}) == "sql"
    assert _route_after_supervisor({"next": "general"}) == "general"


def test_route_after_supervisor_finish_goes_to_end() -> None:
    """supervisor 决策 FINISH 时路由到 END（结束循环）。"""
    from petrochat.app.agent.graph import _route_after_supervisor

    assert _route_after_supervisor({"next": "FINISH"}) == END


def test_route_after_supervisor_missing_next_defaults_to_end() -> None:
    """next 字段缺失时默认 FINISH→END（安全兜底，避免无限循环）。"""
    from petrochat.app.agent.graph import _route_after_supervisor

    assert _route_after_supervisor({}) == END


def test_route_after_general_tools_when_tool_calls() -> None:
    """general 产出含 tool_calls → 路由到 tools（ReAct 循环）。"""
    from petrochat.app.agent.graph import _route_after_general

    state = {
        "messages": [
            AIMessage(content="", tool_calls=[{"name": "x", "args": {}, "id": "1"}])
        ]
    }
    assert _route_after_general(state) == "tools"


def test_route_after_general_supervisor_when_no_tool_calls() -> None:
    """general 产出无 tool_calls → 回 supervisor（让 supervisor 评估是否 FINISH）。"""
    from petrochat.app.agent.graph import _route_after_general

    state = {"messages": [AIMessage(content="已完成", tool_calls=[])]}
    assert _route_after_general(state) == "supervisor"


def test_route_after_general_supervisor_when_no_ai_message() -> None:
    """messages 里没有 AIMessage → 默认回 supervisor。"""
    from petrochat.app.agent.graph import _route_after_general

    state = {"messages": [HumanMessage(content="hi")]}
    assert _route_after_general(state) == "supervisor"


# ===== 循环 Supervisor：图拓扑 =====


def _graph_edge_pairs(g) -> set[tuple[str, str]]:
    """从编译后的 LangGraph 提取 (source, target) 边集合。

    LangGraph 1.x 的 CompiledStateGraph 没有 .edges 属性，
    需要通过 get_graph() 获取结构化表示；边可能是元组或 Edge 对象。
    """
    pairs: set[tuple[str, str]] = set()
    raw = g.get_graph()
    for e in (getattr(raw, "edges", None) or []):
        if isinstance(e, tuple) and len(e) >= 2:
            pairs.add((str(e[0]), str(e[1])))
        elif hasattr(e, "source") and hasattr(e, "target"):
            pairs.add((str(e.source), str(e.target)))
        elif hasattr(e, "parent") and hasattr(e, "child"):
            pairs.add((str(e.parent), str(e.child)))
    return pairs


def test_graph_worker_edges_return_to_supervisor() -> None:
    """qa/sql 执行完回 supervisor（而非 END），让 supervisor 评估是否继续分派。"""
    g = build_graph()
    edges = _graph_edge_pairs(g)
    assert ("qa", "supervisor") in edges, "qa 应回 supervisor"
    assert ("sql", "supervisor") in edges, "sql 应回 supervisor"


def test_graph_general_can_loop_to_tools_and_supervisor() -> None:
    """general 的条件边能到 tools（ReAct）和 supervisor（循环评估）。"""
    g = build_graph()
    edges = _graph_edge_pairs(g)
    assert ("general", "tools") in edges
    assert ("general", "supervisor") in edges


def test_graph_supervisor_can_reach_end() -> None:
    """supervisor 通过 FINISH 能到达 END。"""
    g = build_graph()
    edges = _graph_edge_pairs(g)
    assert ("supervisor", END) in edges, "supervisor 应能通过 FINISH 到达 END"
