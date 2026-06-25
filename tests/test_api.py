"""API 路由结构测试。不发起真实 LLM 调用。"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from test_memory import make_memory_test_engine

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
    assert "/api/memory" in paths
    assert "/api/memory/{memory_id}" in paths
    assert "/api/memory/{memory_id}/disable" in paths
    assert "/api/memory/{memory_id}/events" in paths
    assert "post" in paths["/api/auth/login"]
    assert "get" in paths["/api/auth/me"]
    assert "get" in paths["/api/evaluation/latest"]
    assert "get" in paths["/api/evaluation/failures"]
    assert "get" in paths["/api/evaluation/runs"]
    assert "get" in paths["/api/memory"]
    assert "post" in paths["/api/memory"]
    assert "patch" in paths["/api/memory/{memory_id}"]
    assert "delete" in paths["/api/memory/{memory_id}"]


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
    attribution_counts = {item["type"]: item["count"] for item in data["attributionSummary"]}
    assert attribution_counts["sql"] == 2
    assert attribution_counts["memory"] == 3
    assert data["severitySummary"]["fail"] == 2
    assert data["cases"][0]["riskLevel"] == "fail"
    assert data["cases"][0]["primaryAttribution"]["type"] == "sql"
    assert data["cases"][0]["attributions"][0]["nextStep"]
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


def test_delete_session_checks_user_id(monkeypatch) -> None:
    from petrochat.app.memory import get_conversation_store
    from petrochat.app.memory import store as store_module

    engine = make_memory_test_engine()
    monkeypatch.setattr(store_module, "get_engine", lambda: engine)
    get_conversation_store.cache_clear()

    store = get_conversation_store()
    session_id = store.create_session(user_id="1", title="owned by u1")
    store.append_turn(session_id, "hello", "world")

    denied = client.delete(f"/api/sessions/{session_id}", params={"user_id": "2"})
    assert denied.status_code == 404
    assert store.list_messages(session_id)

    allowed = client.delete(f"/api/sessions/{session_id}", params={"user_id": "1"})
    assert allowed.status_code == 200
    assert allowed.json() == {"deleted": True}

    get_conversation_store.cache_clear()


def test_long_term_memory_api_lifecycle(monkeypatch) -> None:
    from petrochat.app.memory import get_long_term_memory_store
    from petrochat.app.memory import long_term as long_term_module

    engine = make_memory_test_engine()
    monkeypatch.setattr(long_term_module, "get_engine", lambda: engine)
    get_long_term_memory_store.cache_clear()

    create_resp = client.post(
        "/api/memory",
        json={
            "user_id": "1",
            "memory_type": "preference",
            "content": "用户常看炼油一部的动设备任务",
            "source": "manual",
            "confidence": 0.9,
            "metadata": {"department": "炼油一部"},
            "actor_id": "1",
        },
    )
    assert create_resp.status_code == 200
    item = create_resp.json()
    assert item["status"] == "active"
    assert item["metadata"]["department"] == "炼油一部"

    list_resp = client.get("/api/memory", params={"user_id": "1"})
    assert list_resp.status_code == 200
    assert [row["id"] for row in list_resp.json()] == [item["id"]]

    update_resp = client.patch(
        f"/api/memory/{item['id']}",
        json={
            "content": "用户常看炼油一部的动设备和仪表任务",
            "confidence": 0.8,
            "actor_id": "1",
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["confidence"] == 0.8

    disable_resp = client.post(
        f"/api/memory/{item['id']}/disable",
        json={"actor_id": "1", "reason": "用户要求暂停"},
    )
    assert disable_resp.status_code == 200
    assert disable_resp.json()["status"] == "disabled"

    events_resp = client.get(f"/api/memory/{item['id']}/events")
    assert events_resp.status_code == 200
    assert [row["event_type"] for row in events_resp.json()] == ["created", "updated", "disabled"]

    get_long_term_memory_store.cache_clear()


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
                "success_rate": 0.875,
                "error_count": 1,
                "avg_latency_ms": 1234.5,
                "max_latency_ms": 3000,
                "sql_validation_rate": 1.0,
                "sql_table_recall": 0.75,
                "sql_filter_value_recall": 0.5,
                "sql_contract_accuracy": 0.5,
                "sql_execution_accuracy": 0.25,
                "sql_execution_scored_count": 4,
                "rag_recall_at_5": 0.25,
                "rag_mrr": 0.125,
                "rag_evidence_coverage": 0.5,
                "rag_faithfulness_proxy": 0.25,
                "memory_hit_rate": 0.6,
                "memory_required_count": 5,
                "memory_ignore_violation_rate": 0.0,
                "memory_ignore_checked_count": 1,
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
    prediction_by_label = {item["label"]: item for item in data["predictionMetrics"]}
    assert prediction_by_label["Agent 成功率"]["value"] == "88%"
    assert prediction_by_label["SQL 表召回"]["value"] == "75%"
    assert prediction_by_label["SQL 合约准确率"]["value"] == "50%"
    assert prediction_by_label["SQL 执行准确率"]["detail"] == "scored=4"
    assert prediction_by_label["RAG MRR"]["value"] == "12%"
    assert prediction_by_label["Memory Hit Rate"]["detail"] == "required=5"
    assert data["scenarioCounts"] == [{"label": "nl2sql_condition_memory", "value": 4}]

    get_settings.cache_clear()
