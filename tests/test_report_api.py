from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from petrochat.app.api import reports
from petrochat.app.api.auth import resolve_auth_user
from petrochat.app.core.models import AuthUser
from petrochat.app.report.persistence import schema
from petrochat.app.report.store import ReportStore
from petrochat.app.report.worker import ReportWorker


def test_api_auth_owner_conflict_and_download(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}")
    schema.create_all(engine)
    store = ReportStore(engine)
    app = FastAPI()
    app.include_router(reports.router)
    app.dependency_overrides[reports.report_store] = lambda: store
    client = TestClient(app)
    assert client.get("/api/reports").status_code == 401
    user = AuthUser(user_id="1", username="one", role="engineer", authority_flag=0)
    app.dependency_overrides[resolve_auth_user] = lambda: user
    assert (
        client.post("/api/reports", json={"question": "统计数量", "user_id": "2"}).status_code
        == 422
    )
    created = client.post("/api/reports", json={"question": "统计数量"})
    assert created.status_code == 201
    task = created.json()
    assert "lease_token" not in task
    base = f"/api/reports/{task['id']}"
    user.user_id = "2"
    for path in [base, base + "/events", base + "/artifacts/draft", base + "/artifacts/export"]:
        assert client.get(path).status_code == 404
    assert (
        client.post(
            base + "/actions", json={"expected_revision": 0, "action": "cancel"}
        ).status_code
        == 404
    )
    assert client.get("/api/reports").json() == []
    user.user_id = "1"
    root = tmp_path / "reports"
    from types import SimpleNamespace

    monkeypatch.setattr(reports, "get_settings", lambda: SimpleNamespace(report_artifact_dir=root))
    worker = ReportWorker(store, root, lambda q: {"columns": ["count"], "rows": [{"count": 4}]})
    for _ in range(15):
        worker.run_once()
        row = client.get(base).json()
        if row["status"] == "awaiting_input":
            if row["state_json"]["review"]["stage"] == "draft":
                draft = client.get(base + "/artifacts/draft")
                assert draft.status_code == 200 and "4" in draft.text
                assert client.get(base + "/artifacts/export").status_code == 404
            payload = {"expected_revision": row["revision"], "action": "approve"}
            assert client.post(base + "/actions", json=payload).status_code == 200
            assert client.post(base + "/actions", json=payload).status_code == 409
        if row["status"] == "completed":
            break
    assert row["status"] == "completed"
    exported = client.get(base + "/artifacts/export")
    assert exported.status_code == 200 and exported.content[:2] == b"PK"
    assert len(client.get(base + "/events").json()) > 5
    assert client.get(base + "/events?after=9999999").json() == []


def test_disabled_report_service(monkeypatch):
    from types import SimpleNamespace

    import pytest
    from fastapi import HTTPException

    monkeypatch.setattr(reports, "get_settings", lambda: SimpleNamespace(report_enabled=False))
    with pytest.raises(HTTPException) as error:
        reports.report_store()
    assert error.value.status_code == 503
