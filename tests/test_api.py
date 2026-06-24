"""API 路由结构测试。不发起真实 LLM 调用。"""

from __future__ import annotations

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
    assert "post" in paths["/api/auth/login"]
    assert "get" in paths["/api/auth/me"]


def test_dev_login_returns_local_token(monkeypatch) -> None:
    from petrochat.app.core.config import get_settings

    monkeypatch.setenv("APP_ENV", "dev")
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
