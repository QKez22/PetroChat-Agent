"""API 路由结构测试。不发起真实 LLM 调用。"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from petrochat.main import app

client = TestClient(app)


def test_health_still_works() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200


def test_chat_validates_empty_question() -> None:
    resp = client.post("/api/chat", json={"question": ""})
    assert resp.status_code == 422


def test_chat_validates_long_question() -> None:
    resp = client.post("/api/chat", json={"question": "x" * 2001})
    assert resp.status_code == 422


def test_chat_endpoints_in_openapi() -> None:
    """通过 OpenAPI schema 验证两个聊天端点都被注册（比 app.routes 内部结构稳定）。"""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/api/chat" in paths
    assert "/api/chat/stream" in paths
    assert "/api/sessions" in paths
    assert "/api/sessions/{session_id}" in paths
    # 都应支持 POST
    assert "post" in paths["/api/chat"]
    assert "post" in paths["/api/chat/stream"]
    assert "get" in paths["/api/sessions"]
    assert "get" in paths["/api/sessions/{session_id}"]
    assert "delete" in paths["/api/sessions/{session_id}"]


def test_auth_endpoints_in_openapi() -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/api/auth/login" in paths
    assert "/api/auth/me" in paths
    assert "/api/evaluation/latest" in paths
    assert "/api/evaluation/failures" in paths
    assert "/api/evaluation/runs" in paths
    assert "post" in paths["/api/auth/login"]
    assert "get" in paths["/api/auth/me"]
    assert "get" in paths["/api/evaluation/latest"]
    assert "get" in paths["/api/evaluation/failures"]
    assert "get" in paths["/api/evaluation/runs"]


def test_dev_login_returns_local_token(monkeypatch) -> None:
    from petrochat.app.core.config import get_settings

    monkeypatch.setenv("APP_ENV", "dev")
    get_settings.cache_clear()


def test_evaluation_failures_reads_prediction_samples(monkeypatch, tmp_path) -> None:
    from petrochat.app.core.config import get_settings

    prediction_path = tmp_path / "predictions.jsonl"
    rows = [
        {
            "dialogue_id": "d1",
            "turn_id": "1",
            "mode": "agent",
            "scenario_type": "nl2sql_condition_memory",
            "question": "查询设备相关任务",
            "route": "sql",
            "answer": "",
            "sql": "",
            "status": "ok",
            "latency_ms": 120,
        },
        {
            "dialogue_id": "d2",
            "turn_id": "2",
            "mode": "agent",
            "scenario_type": "rag_context_memory",
            "question": "规范里怎么要求？",
            "route": "qa",
            "answer": "需要引用制度条款",
            "retrieved": [],
            "status": "ok",
            "latency_ms": 20,
        },
        {
            "dialogue_id": "d3",
            "turn_id": "1",
            "mode": "agent",
            "scenario_type": "nl2sql_condition_memory",
            "question": "只读查询",
            "route": "sql",
            "answer": "已查询",
            "sql": "UPDATE affair_task SET status = 'done'",
            "status": "ok",
            "latency_ms": 10,
        },
    ]
    prediction_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )
    monkeypatch.setenv("EVAL_PREDICTIONS_PATH", str(prediction_path))
    get_settings.cache_clear()

    resp = client.get("/api/evaluation/failures", params={"limit": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert data["totalPredictions"] == 3
    assert data["returnedCount"] == 2
    assert data["failureCount"] == 2
    assert data["cases"][0]["riskLevel"] == "fail"
    assert data["cases"][0]["sqlSummary"]["present"] is False
    assert data["cases"][0]["traceHint"]["sessionId"] == "eval-d1"
    assert "sql" not in data["cases"][0]
    assert any("SQL" in reason for reason in data["cases"][0]["reasons"])

    get_settings.cache_clear()


def test_evaluation_runs_reads_local_summaries(monkeypatch, tmp_path) -> None:
    from petrochat.app.core.config import get_settings

    summary_path = tmp_path / "golden_eval_summary.json"
    prediction_path = tmp_path / "predictions.jsonl"
    summary_path.write_text(
        json.dumps({
            "dataset_profile": {
                "dialogue_count": 5,
                "turn_count": 12,
            },
            "prediction_metrics": {
                "prediction_count": 12,
                "sql_validation_rate": 0.8,
                "sql_table_recall": 0.75,
                "rag_recall_at_5": 0.5,
            },
            "declared_validation_summary": {"generated_at": "2026-06-25T10:00:00"},
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    prediction_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("EVAL_RESULTS_PATH", str(summary_path))
    monkeypatch.setenv("EVAL_PREDICTIONS_PATH", str(prediction_path))
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_PROJECT", "petrochat-test")
    get_settings.cache_clear()

    resp = client.get("/api/evaluation/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["returnedCount"] == 1
    run = data["runs"][0]
    assert run["status"] == "scored"
    assert run["generatedAt"] == "2026-06-25 10:00"
    assert run["dataset"] == {"dialogues": 5, "turns": 12}
    assert run["metrics"]["sqlValidationRate"] == "80%"
    assert run["artifacts"]["summary"] is True
    assert run["artifacts"]["predictions"] is True
    assert run["traceHint"]["enabled"] is True
    assert run["traceHint"]["project"] == "petrochat-test"

    get_settings.cache_clear()

    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["token"]
    assert data["user"]["role"] == "admin"
    assert data["user"]["authority_flag"] == 1
    assert "用户管理" in data["user"]["permissions"]

    me_resp = client.get("/api/auth/me", params={"token": data["token"]})
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == "admin"


def test_delete_session_checks_user_id(monkeypatch, tmp_path) -> None:
    from petrochat.app.core.config import get_settings
    from petrochat.app.memory import get_conversation_store

    monkeypatch.setenv("SESSION_STORE_PATH", str(tmp_path / "sessions.sqlite3"))
    get_settings.cache_clear()
    get_conversation_store.cache_clear()

    store = get_conversation_store()
    session_id = store.create_session(user_id="u1", title="owned by u1")
    store.append_turn(session_id, "hello", "world")

    denied = client.delete(f"/api/sessions/{session_id}", params={"user_id": "u2"})
    assert denied.status_code == 404
    assert store.list_messages(session_id)

    allowed = client.delete(f"/api/sessions/{session_id}", params={"user_id": "u1"})
    assert allowed.status_code == 200
    assert allowed.json() == {"deleted": True}

    get_conversation_store.cache_clear()
    get_settings.cache_clear()


def test_latest_evaluation_reads_summary(monkeypatch, tmp_path) -> None:
    from petrochat.app.core.config import get_settings

    summary_path = tmp_path / "golden_eval_summary.json"
    summary_path.write_text(
        json.dumps({
            "dataset_profile": {
                "dialogue_count": 2,
                "turn_count": 8,
                "sql_expectation_count": 3,
                "rag_evidence_count": 4,
                "memory_state_count": 8,
                "scenario_counts": {"nl2sql_condition_memory": 4},
            },
            "sql_contract": {
                "template_count": 3,
                "template_valid_count": 3,
                "template_valid_rate": 1.0,
                "write_operation_violations": 0,
                "select_star_violations": 0,
            },
            "memory_contract": {
                "requires_memory_use_turns": 5,
                "requires_memory_ignore_turns": 1,
            },
            "rag_contract": {"evidence_count": 4},
            "prediction_metrics": {
                "prediction_count": 8,
                "sql_validation_rate": 1.0,
                "sql_table_recall": 0.75,
                "sql_filter_value_recall": 0.5,
                "rag_recall_at_5": 0.25,
            },
            "declared_validation_summary": {"generated_at": "2026-06-24T15:27:01"},
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setenv("EVAL_RESULTS_PATH", str(summary_path))
    get_settings.cache_clear()

    resp = client.get("/api/evaluation/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dataset"]["dialogues"] == 2
    assert data["contractMetrics"][0]["value"] == "100%"
    assert data["predictionMetrics"][2]["value"] == "75%"
    assert data["scenarioCounts"] == [{"label": "nl2sql_condition_memory", "value": 4}]

    get_settings.cache_clear()
