import pytest
from sqlalchemy import create_engine, update

from petrochat.app.report.persistence import schema
from petrochat.app.report.store import Conflict, ReportStore, tasks


@pytest.fixture
def store(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'tasks.db'}")
    schema.create_all(engine)
    return ReportStore(engine)


def test_owner_revision_and_audit(store):
    row = store.create("1", "统计各专业事务数")
    assert store.list("2") == []
    with pytest.raises(KeyError):
        store.action(row["id"], "2", 0, "cancel")
    row = store.action(row["id"], "1", 0, "pause")
    with pytest.raises(Conflict):
        store.action(row["id"], "1", 0, "resume")
    row = store.action(row["id"], "1", row["revision"], "resume")
    assert row["status"] == "queued"
    assert len(store.history(row["id"], "1")) == 3


def test_scoped_claim_never_picks_another_task(store):
    real = store.create("1", "existing user task")
    smoke = store.create("0", "isolated smoke task")
    assert store.claim(task_id="absent") is None
    assert store.claim(task_id=smoke["id"])["id"] == smoke["id"]
    assert store.get(real["id"], "1")["status"] == "queued"


def test_expired_worker_cannot_write_or_complete(store):
    from langgraph.checkpoint.base import empty_checkpoint

    from petrochat.app.report.store import LeasedSaver

    task = store.create("1", "统计各专业事务数")
    first = store.claim()
    assert store.claim() is None
    with store.engine.begin() as conn:
        conn.execute(update(tasks).where(tasks.c.id == task["id"]).values(lease_until=0))
    second = store.claim()
    assert first["lease_token"] != second["lease_token"]
    with pytest.raises(Conflict):
        store.finish_step(task["id"], first["lease_token"], "completed", {})
    with pytest.raises(Conflict):
        LeasedSaver(store, task["id"], first["lease_token"]).put(
            {"configurable": {"thread_id": task["id"]}}, empty_checkpoint(), {}, {}
        )
    cancelled = store.action(task["id"], "1", second["revision"], "cancel")
    assert cancelled["status"] == "cancelled"
    with pytest.raises(Conflict):
        store.finish_step(task["id"], second["lease_token"], "completed", {})


def test_pause_is_boundary_and_retries_are_bounded(store):
    task = store.create("1", "统计各专业事务数")
    claimed = store.claim()
    paused = store.action(task["id"], "1", claimed["revision"], "pause")
    assert paused["status"] == "pause_requested"
    done = store.finish_step(task["id"], claimed["lease_token"], "queued", {"generation": 0})
    assert done["status"] == "paused" and store.claim() is None
    store.action(task["id"], "1", done["revision"], "resume")
    for _ in range(3):
        claim = store.claim()
        store.finish_step(task["id"], claim["lease_token"], "queued", {"generation": 0}, error=True)
        with store.engine.begin() as conn:
            conn.execute(update(tasks).where(tasks.c.id == task["id"]).values(due_at=0))
    assert store.claim() is None
    assert store.get(task["id"], "1")["status"] == "failed"
