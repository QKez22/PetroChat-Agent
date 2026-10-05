"""P2 长对话、受保护上下文与报表回读回归。"""

from __future__ import annotations

import copy
import json

import pytest
from langchain_core.documents import Document
from langchain_core.messages import ToolMessage

from petrochat.app.agent import build_initial_state
from petrochat.app.agent.prompts import format_context
from petrochat.app.core.budget import BudgetExceeded, RunBudget, budget_scope
from petrochat.app.core.config import get_settings
from petrochat.app.core.context import prepare_payload
from petrochat.app.memory.constraints import active_constraints, stored_constraints
from petrochat.app.memory.outcome import decode_answer, encode_answer
from petrochat.app.tools.report_page import compact_report_messages, read_report_page


def test_old_answers_can_shrink_without_mutating_original(monkeypatch):
    monkeypatch.setenv("CONTEXT_INPUT_TOKEN_BUDGET", "600")
    get_settings.cache_clear()
    payload = {
        "messages": [
            {"role": "user", "content": "只看炼油二部，按部门分组"},
            {"role": "assistant", "content": "无关解释" * 1000},
            {"role": "user", "content": "解释 ITPM"},
        ]
    }
    original = copy.deepcopy(payload)
    result, stats = prepare_payload(payload)
    assert payload == original
    assert result["messages"][0] == original["messages"][0]
    assert result["messages"][-1] == original["messages"][-1]
    assert stats["input_estimated_after"] <= 600 < stats["input_estimated_before"]


@pytest.mark.parametrize("kind", ["question", "schema", "followup", "tool_pair"])
def test_protected_context_is_never_silently_truncated(monkeypatch, kind):
    monkeypatch.setenv("CONTEXT_INPUT_TOKEN_BUDGET", "200")
    get_settings.cache_clear()
    payload = {"messages": [{"role": "user", "content": "解释 ITPM"}]}
    if kind == "question":
        payload["messages"][0]["content"] *= 300
    elif kind == "schema":
        payload["tools"] = [{"name": "query", "description": "原始过滤约束" * 300}]
    elif kind == "followup":
        payload["messages"] = [
            {"role": "assistant", "content": "证据" * 1000},
            {"role": "user", "content": "继续分析刚才结果"},
        ]
    else:
        payload["messages"].extend(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {"id": "call-1", "function": {"name": "retrieve", "arguments": "{}"}}
                    ],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": "规范证据" * 1000},
            ]
        )
    original = copy.deepcopy(payload)
    with pytest.raises(BudgetExceeded, match="上下文"):
        prepare_payload(payload)
    assert original == payload


def test_department_replacement_and_explicit_clear():
    history = [
        {"role": "user", "content": "按部门统计炼油一部设备数量"},
        {"role": "assistant", "content": "改为炼油三部"},
        {"role": "user", "content": "改为炼油二部"},
    ]
    current = active_constraints(history)
    assert "炼油二部" in current["departments"]
    assert "炼油一部" not in json.dumps(current, ensure_ascii=False)
    assert current["groups"] == '["部门"]'
    assert "departments" not in active_constraints(history, "不限部门")
    assert not active_constraints(history, "换个话题，解释 ITPM")


def test_outcome_encoding_is_backward_compatible():
    for status in ("completed", "partial", "failed"):
        assert decode_answer(encode_answer("正文", status)) == ("正文", status)
    assert decode_answer("旧回答") == ("旧回答", "unknown")
    assert decode_answer("PETROCHAT_MESSAGE_V1\ninvalid")[1] == "unknown"


def test_unknown_numeric_constraint_is_preserved_verbatim():
    original = "压力不得超过 1 MPa，只有停机状态才允许执行"
    initial = active_constraints([{"role": "user", "content": original}])
    updated = active_constraints([{"role": "user", "content": "继续查询"}], initial=initial)
    assert original in "\n".join(updated.values())


def test_long_conversation_preserves_latest_constraints_and_failure(monkeypatch):
    from test_memory import make_memory_test_engine

    from petrochat.app.memory import (
        ConversationStore,
        fit_prompt_context,
        refresh_conversation_summary,
    )

    monkeypatch.setenv("SHORT_TERM_TURNS", "2")
    get_settings.cache_clear()
    store = ConversationStore(engine=make_memory_test_engine())
    session = store.create_session(user_id="1", title="long")
    for i in range(12):
        question = (
            "按部门统计炼油一部事务数量"
            if i == 0
            else "改为炼油二部"
            if i == 5
            else f"继续问题 {i}"
        )
        store.append_turn(session, question, "统计未完成：需要确认映射", status="partial")
        refresh_conversation_summary(session, store=store, force=True)
    summary = store.get_summary(session).summary_text
    assert stored_constraints(summary)["departments"] == '["炼油二部"]'
    assert "partial; 不得视为已完成" in summary
    assert "已确认事实" not in summary
    messages = store.recent_messages(session, 2)
    assert messages[-1].status == "partial" and not messages[-1].content.startswith(
        "PETROCHAT_MESSAGE"
    )
    fitted = fit_prompt_context(
        question="继续统计",
        history=[{"role": m.role, "content": m.content} for m in messages],
        conversation_summary=summary,
        long_term_context="",
    )
    state = build_initial_state(
        "继续统计", history=fitted.history, conversation_summary=fitted.conversation_summary
    )
    sql_history = json.dumps(state["short_term_messages"], ensure_ascii=False)
    assert "炼油二部" in sql_history and "炼油一部" not in sql_history


def test_report_preview_is_reversible_and_request_scoped():
    data = {
        "sql": "SELECT code, count FROM demo",
        "columns": ["code", "count"],
        "rows": [{"code": str(i), "count": i} for i in range(60)],
    }
    message = ToolMessage(
        content="完整表格" * 300, tool_call_id="report-one", artifact={"query_result": data}
    )
    budget = RunBudget(12, 8, 2, 180)
    with budget_scope(budget):
        preview = compact_report_messages([message])[0]
        info = json.loads(preview.content)
        assert not info["complete"] and len(info["preview_rows"]) == 5
        assert preview.tool_call_id == message.tool_call_id
        assert message.content == "完整表格" * 300
        assert message.artifact["query_result"]["rows"] == data["rows"]
        page = json.loads(read_report_page.invoke({"report_id": info["report_id"], "offset": 55}))
        assert page["rows"] == data["rows"][55:] and not page["has_more"]
    with budget_scope(RunBudget(12, 8, 2, 180)):
        assert "❌" in read_report_page.invoke({"report_id": info["report_id"]})


def test_rag_deduplication_preserves_conditions_units_and_source():
    doc = Document(
        page_content="仅在停机状态下，压力不得超过 1 MPa。",
        metadata={"section_number": "1.2", "source_doc": "规范A"},
    )
    result = format_context([doc, doc])
    assert result.count(doc.page_content) == 1
    assert "[1.2] 规范A" in result


@pytest.mark.asyncio
async def test_report_page_tool_obeys_graph_tool_budget():
    from langchain_core.messages import AIMessage
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode

    from petrochat.app.agent.runtime import guarded_async_tool, tool_error

    node = ToolNode(
        [read_report_page], awrap_tool_call=guarded_async_tool, handle_tool_errors=tool_error
    )
    builder = StateGraph(MessagesState)
    builder.add_node("tools", node)
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    graph = builder.compile()
    budget = RunBudget(12, 1, 2, 180)
    budget.report_cache["report"] = {"columns": ["value"], "rows": [{"value": 42}]}
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "read1", "name": "read_report_page", "args": {"report_id": "report"}}
                ],
            )
        ]
    }
    with budget_scope(budget):
        result = await graph.ainvoke(state)
        assert json.loads(result["messages"][-1].content)["rows"] == [{"value": 42}]
        assert budget.tool_calls == 1
        with pytest.raises(BudgetExceeded):
            await graph.ainvoke(state)
