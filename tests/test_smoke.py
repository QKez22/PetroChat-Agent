"""脚手架冒烟测试：验证 FastAPI 应用能成功创建并响应 /health。"""

from fastapi.testclient import TestClient

from petrochat.main import app

client = TestClient(app)


def test_health() -> None:
    """健康检查接口应返回 200 与 ok 状态。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root() -> None:
    """根路由应返回项目元信息。"""
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "PetroChat-Agent"
    assert "stage" in body
