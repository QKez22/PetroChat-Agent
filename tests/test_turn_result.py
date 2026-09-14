"""P0 回归: 真实图事件、接口一致性和并发报表隔离。"""

from __future__ import annotations

import asyncio
import importlib
import json
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, convert_to_openai_messages

from petrochat.app.agent.result import build_turn_result
from petrochat.app.api import routes
from petrochat.app.api.auth import _encode_local_token
from petrochat.app.core.models import AuthUser, ChatRequest
from petrochat.app.sql.agent import Nl2SqlResult
from petrochat.main import app


class TurnStore:
    def __init__(self):
        self.turns = []

    def ensure_session(self, session_id, **kwargs):
        return session_id or "test-session"

    def recent_messages(self, *args):
        return [
            SimpleNamespace(role="user", content="old question"),
            SimpleNamespace(role="assistant", content="OLD ANSWER"),
        ]

    def get_summary(self, *args):
        return None

    def append_turn(self, session_id, question, answer, **kwargs):
        self.turns.append((session_id, question, answer))


@pytest.fixture
def runtime(monkeypatch):
    # sse-starlette 2.x 的退出事件绑定事件循环, TestClient 每个测试创建新循环。
    from sse_starlette.sse import AppStatus

    monkeypatch.setattr(AppStatus, "should_exit_event", None)
    graph_module = importlib.import_module("petrochat.app.agent.graph")
    sql_module = importlib.import_module("petrochat.app.agent.nodes.sql_node")
    tool_module = importlib.import_module("petrochat.app.tools.sql_tool")
    store = TurnStore()
    written = []
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setattr(routes, "get_conversation_store", lambda: store)
    monkeypatch.setattr(routes, "recall_long_term_memories", lambda **kwargs: ([], ""))
    monkeypatch.setattr(routes, "_refresh_summary_after_turn", lambda *args: None)
    monkeypatch.setattr(
        routes, "write_memory_candidates", lambda **kwargs: written.append(kwargs) or []
    )

    def query(question):
        # 模拟 SQL 内部模型输出, 必须从用户正文中过滤掉。
        FakeListChatModel(responses=["INTERNAL SQL GENERATION"]).invoke(question)
        return Nl2SqlResult(
            ok=True,
            sql="SELECT category, count FROM demo",
            reasoning="统计",
            columns=["category", "count"],
            rows=[{"category": question, "count": 1}, {"category": "other", "count": 2}],
            row_count=2,
        )

    monkeypatch.setattr(sql_module, "nl2sql", query)
    monkeypatch.setattr(tool_module, "nl2sql", query)

    def supervisor(state):
        FakeListChatModel(responses=["INTERNAL ROUTING"]).invoke("route")
        step = state.get("supervisor_step", 0)
        scenario = state["question"].split(":")[0]
        sequence = {
            "qa": ["qa"],
            "sql": ["sql"],
            "compound": ["qa", "sql"],
            "general": ["general"],
            "failed": ["sql"],
            "multi": ["sql", "sql"],
        }[scenario]
        return {
            "next": sequence[step] if step < len(sequence) else "FINISH",
            "supervisor_step": step + 1,
        }

    def qa(state):
        return {"messages": [AIMessage(content="规范依据 [1.2]。")], "citations": ["《规范》[1.2]"]}

    def general(state):
        if isinstance(state["messages"][-1], ToolMessage):
            return {"messages": [AIMessage(content="已完成工具查询。")]}
        return {
            "messages": [
                AIMessage(
                    content="TOOL PREFACE",
                    tool_calls=[
                        {
                            "name": "query_database",
                            "args": {"question": state["question"]},
                            "id": "query-1",
                        }
                    ],
                )
            ]
        }

    monkeypatch.setattr(graph_module, "supervisor_node", supervisor)
    monkeypatch.setattr(graph_module, "qa_node", qa)
    monkeypatch.setattr(graph_module, "general_node", general)
    graph_module.build_graph.cache_clear()
    user = AuthUser(user_id="2", username="test", role="engineer", authority_flag=0, permissions=[])
    return SimpleNamespace(
        store=store,
        written=written,
        user=user,
        sql_module=sql_module,
        tool_module=tool_module,
        query=query,
    )


def decode_sse(text):
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in fields and "data" in fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


@pytest.mark.parametrize("scenario", ["qa", "sql", "compound", "general", "multi"])
def test_http_stream_and_nonstream_share_answer_and_artifacts(runtime, scenario):
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_encode_local_token(runtime.user)}"}
    request = {"question": scenario, "session_id": "session-test"}
    response = client.post("/api/chat", json=request, headers=headers)
    assert response.status_code == 200
    normal = response.json()
    streamed = client.post("/api/chat/stream", json=request, headers=headers)
    events = decode_sse(streamed.text)
    assert events[-1][0] == "done", events
    final = next(data for event, data in events if event == "result")
    meta = next(data for event, data in events if event == "meta")
    for key in ("answer", "citations", "artifacts"):
        assert final[key] == normal[key]
    assert "".join(data["text"] for event, data in events if event == "token") == normal["answer"]
    assert "OLD ANSWER" not in normal["answer"]
    assert "INTERNAL" not in normal["answer"]
    assert "TOOL PREFACE" not in normal["answer"]
    assert runtime.store.turns[-1][2] == runtime.store.turns[-2][2] == normal["answer"]
    assert runtime.written[-1]["answer"] == normal["answer"]
    assert meta["artifacts"] == final["artifacts"]
    if scenario == "compound":
        assert "规范依据" in normal["answer"] and "| category | count |" in normal["answer"]
    if scenario == "multi":
        assert len(normal["artifacts"]) == 2
    if scenario != "qa":
        assert normal["artifacts"][0]["chart_data_uri"].startswith("data:image/png;base64,")
        assert "base64" not in normal["answer"]


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["sql", "general"])
async def test_concurrent_stream_and_nonstream_reports_are_isolated(runtime, monkeypatch, scenario):
    barrier = Barrier(2, timeout=15)

    def concurrent_query(question):
        barrier.wait()
        return runtime.query(question)

    monkeypatch.setattr(runtime.sql_module, "nl2sql", concurrent_query)
    monkeypatch.setattr(runtime.tool_module, "nl2sql", concurrent_query)

    async def stream():
        return [
            (event["event"], json.loads(event["data"]))
            async for event in routes._stream_events(
                ChatRequest(question=f"{scenario}:B", session_id="B"), runtime.user
            )
        ]

    normal, events = await asyncio.gather(
        routes.chat(ChatRequest(question=f"{scenario}:A", session_id="A"), runtime.user), stream()
    )
    assert events[-1][0] == "done", events
    streamed = next(data for kind, data in events if kind == "result")
    assert normal.artifacts[0].title == f"{scenario}:A"
    assert streamed["artifacts"][0]["title"] == f"{scenario}:B"
    assert normal.artifacts[0].chart_data_uri != streamed["artifacts"][0]["chart_data_uri"]
    assert f"{scenario}:B" not in normal.artifacts[0].markdown
    assert f"{scenario}:A" not in streamed["artifacts"][0]["markdown"]


def test_tool_artifact_does_not_enter_model_payload(runtime):
    message = runtime.tool_module.query_database.invoke(
        {
            "type": "tool_call",
            "name": "query_database",
            "id": "one",
            "args": {"question": "general"},
        }
    )
    assert message.artifact["reports"][0]["chart_data_uri"]
    payload = convert_to_openai_messages([message])
    assert "base64" not in json.dumps(payload)


def test_failed_query_does_not_reuse_previous_report(runtime, monkeypatch):
    runtime.tool_module.query_database.invoke({"question": "general"})
    monkeypatch.setattr(
        runtime.sql_module,
        "nl2sql",
        lambda question: Nl2SqlResult(ok=False, stage="validate", error="blocked"),
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_encode_local_token(runtime.user)}"}
    events = decode_sse(
        client.post("/api/chat/stream", json={"question": "failed"}, headers=headers).text
    )
    final = next(data for event, data in events if event == "result")
    meta = next(data for event, data in events if event == "meta")
    assert "查询失败" in final["answer"]
    assert final["artifacts"] == []
    assert "chart_data_uri" not in meta


def test_empty_current_turn_never_returns_previous_answer():
    result = build_turn_result(
        {"messages": [HumanMessage("old"), AIMessage("old answer"), HumanMessage("new")]}
    )
    assert result.answer == ""


def test_partial_result_is_consistent_and_not_written_to_long_term_memory(runtime, monkeypatch):
    from petrochat.app.agent.nodes.supervisor_node import RouteDecision, supervisor_node
    from petrochat.app.core import get_settings
    from petrochat.app.core.budget import current_budget

    graph_module = importlib.import_module("petrochat.app.agent.graph")
    supervisor_module = importlib.import_module("petrochat.app.agent.nodes.supervisor_node")

    class Planner:
        def with_structured_output(self, *args, **kwargs):
            return self

        def invoke(self, messages):
            current_budget().reserve("model")
            return RouteDecision(
                next="qa",
                reasoning="两项任务",
                tasks=[
                    {"worker": "qa", "instruction": "解释规则"},
                    {"worker": "sql", "instruction": "统计事务"},
                ],
            )

    def blocked_query(question):
        current_budget().reserve("model")
        raise AssertionError("预算耗尽后不应查询")

    monkeypatch.setenv("AGENT_MODEL_CALL_LIMIT", "1")
    get_settings.cache_clear()
    monkeypatch.setattr(supervisor_module, "get_chat_llm", Planner)
    monkeypatch.setattr(supervisor_module, "review_plan", lambda *args: [])
    monkeypatch.setattr(graph_module, "supervisor_node", supervisor_node)
    monkeypatch.setattr(
        graph_module,
        "qa_node",
        lambda state: {
            "messages": [AIMessage(content="规范依据 [1.2]。")],
            "retrieved": [{"content": "依据"}],
        },
    )
    monkeypatch.setattr(runtime.sql_module, "nl2sql", blocked_query)
    graph_module.build_graph.cache_clear()
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_encode_local_token(runtime.user)}"}
    request = {"question": "解释规则并统计事务"}
    response = client.post("/api/chat", json=request, headers=headers)
    assert response.status_code == 200
    normal = response.json()
    events = decode_sse(client.post("/api/chat/stream", json=request, headers=headers).text)
    assert events[-1][0] == "done", events
    final = next(data for kind, data in events if kind == "result")
    meta = next(data for kind, data in events if kind == "meta")
    for key in ("answer", "status", "tasks", "usage", "termination_reason"):
        assert normal[key] == final[key]
    assert normal["status"] == meta["status"] == "partial"
    assert normal["usage"] == {"model_calls": 1, "tool_calls": 0}
    assert [t["status"] for t in normal["tasks"]] == ["completed", "blocked"]
    assert "规范依据" in normal["answer"] and "上限" in normal["termination_reason"]
    assert not runtime.written
    assert len(runtime.store.turns) == 2


def test_graph_error_emits_error_without_success_result(runtime, monkeypatch):
    def fail(question):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(runtime.sql_module, "nl2sql", fail)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_encode_local_token(runtime.user)}"}
    events = decode_sse(
        client.post("/api/chat/stream", json={"question": "sql"}, headers=headers).text
    )
    assert events[-1][0] == "error"
    assert not any(event in {"done", "result"} for event, _ in events)
    assert not runtime.store.turns
