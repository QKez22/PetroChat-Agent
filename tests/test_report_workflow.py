import io
import zipfile

import pytest
from sqlalchemy import create_engine, update

from petrochat.app.report.persistence import schema
from petrochat.app.report.store import Conflict, ReportStore, tasks
from petrochat.app.report.worker import ReportWorker
from petrochat.app.report.workflow import ArtifactStore


@pytest.fixture
def setup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'workflow.db'}")
    schema.create_all(engine)
    store = ReportStore(engine)
    calls = []

    def query(question):
        calls.append(question)
        return {
            "columns": ["dept", "count"],
            "rows": [{"dept": "=BAD()", "count": 10}, {"dept": "B", "count": 5}],
            "sql": "SELECT dept, count FROM allowed_table",
        }

    root = tmp_path / "artifacts"
    return store, root, query, calls


def advance(worker, store, task_id, target):
    for _ in range(15):
        row = store.get(task_id, "1")
        if row["status"] == target:
            return row
        worker.run_once()
    raise AssertionError(store.get(task_id, "1"))


def test_two_gates_pause_restart_export_and_revision(setup):
    store, root, query, calls = setup
    task = store.create("1", "统计各专业事务数量")
    worker = ReportWorker(store, root, query)
    plan = advance(worker, store, task["id"], "awaiting_input")
    assert plan["state_json"]["review"]["stage"] == "plan" and calls == []
    store.action(task["id"], "1", plan["revision"], "approve")
    with pytest.raises(Conflict):
        store.action(task["id"], "1", plan["revision"], "approve")
    worker.run_once()  # approval checkpoint
    worker.run_once()  # fixed query snapshot
    current = store.get(task["id"], "1")
    paused = store.action(task["id"], "1", current["revision"], "pause")
    assert calls == [task["question"]] and paused["status"] == "paused"
    assert not worker.run_once()
    store.action(task["id"], "1", paused["revision"], "resume")
    # Simulate runtime reconstruction, then finish without querying again.
    worker = ReportWorker(ReportStore(store.engine), root, query)
    draft = advance(worker, store, task["id"], "awaiting_input")
    assert draft["state_json"]["review"]["stage"] == "draft"
    files = ArtifactStore(store, root, draft, "")
    assert "10" in files.read(draft["state_json"]["artifacts"]["draft"]).decode()
    store.action(task["id"], "1", draft["revision"], "approve")
    done = advance(worker, store, task["id"], "completed")
    export = files.read(done["state_json"]["artifacts"]["export"])
    with zipfile.ZipFile(io.BytesIO(export)) as archive:
        assert set(archive.namelist()) == {"report.md", "data.csv", "chart.png", "provenance.json"}
        assert "'=BAD()" in archive.read("data.csv").decode("utf-8-sig")
    assert len(calls) == 1
    with pytest.raises(Conflict):
        store.action(task["id"], "1", done["revision"], "resume")


def test_revision_creates_new_snapshot_and_requires_approval(setup):
    store, root, query, calls = setup
    task = store.create("1", "原统计需求")
    worker = ReportWorker(store, root, query)
    plan = advance(worker, store, task["id"], "awaiting_input")
    store.action(task["id"], "1", plan["revision"], "approve")
    draft = advance(worker, store, task["id"], "awaiting_input")
    original = draft["state_json"]["artifacts"]["snapshot"]
    revised = store.action(task["id"], "1", draft["revision"], "revise", "新统计需求")
    assert revised["state_json"] == {"generation": 1}
    plan = advance(worker, store, task["id"], "awaiting_input")
    assert len(calls) == 1
    store.action(task["id"], "1", plan["revision"], "approve")
    draft = advance(worker, store, task["id"], "awaiting_input")
    assert draft["state_json"]["artifacts"]["snapshot"] != original
    assert calls == ["原统计需求", "新统计需求"]


def test_crash_after_query_artifact_commit_does_not_requery(setup, monkeypatch):
    store, root, query, calls = setup
    task = store.create("1", "统计各专业事务数量")
    worker = ReportWorker(store, root, query)
    plan = advance(worker, store, task["id"], "awaiting_input")
    store.action(task["id"], "1", plan["revision"], "approve")
    worker.run_once()
    original = ArtifactStore.put

    def crashing_put(self, kind, data):
        result = original(self, kind, data)
        if kind == "snapshot":
            raise RuntimeError("simulated crash after durable artifact")
        return result

    monkeypatch.setattr(ArtifactStore, "put", crashing_put)
    worker.run_once()
    monkeypatch.setattr(ArtifactStore, "put", original)
    with store.engine.begin() as conn:
        conn.execute(update(tasks).where(tasks.c.id == task["id"]).values(due_at=0))
    advance(worker, store, task["id"], "awaiting_input")
    assert len(calls) == 1
