import time

import pytest
from sqlalchemy import select

from test_memory import make_memory_test_engine
from petrochat.app.core import get_settings
from petrochat.app.memory.long_term import LongTermMemoryStore
from petrochat.app.memory.sync import MemorySyncWorker, enqueue, fingerprint, jobs, schema
from petrochat.app.memory.validity import is_effective


class Index:
    enabled = True

    def __init__(self):
        self.rows = {}
        self.fail = False
        self.during = None

    def indexed_state(self, user_id, memory_id):
        return self.rows.get((user_id, memory_id), [])

    def sync_current(self, item, *, memory_id, user_id):
        if self.fail:
            raise TimeoutError("secret must not be logged")
        if self.during:
            callback, self.during = self.during, None
            callback()
        self.rows[(user_id, memory_id)] = [fingerprint(item)] if item and is_effective(item) else []

    def iter_index_keys(self, page_size):
        yield from list(self.rows)

    def remove_index_key(self, user_id, memory_id):
        self.rows.pop((user_id, memory_id), None)


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(get_settings(), "memory_sync_enabled", True)
    engine = make_memory_test_engine()
    schema.create_all(engine)
    store, index = LongTermMemoryStore(engine), Index()
    return store, index


def test_transactional_enqueue_failure_retry_and_delete(setup):
    store, index = setup
    item = store.create_memory(user_id="1", memory_type="preference", content="Concise answers preferred")
    clock = [time.time() + 1]
    worker = MemorySyncWorker(store, index, clock=lambda: clock[0])
    index.fail = True
    assert worker.run_once()["failed"] == 1
    with store.engine.connect() as conn:
        row = conn.execute(select(jobs)).mappings().one()
    assert row["pending"] == 1 and row["last_error"] == "TimeoutError"
    assert worker.run_once()["failed"] == 0  # backoff
    index.fail = False
    clock[0] += 10
    assert worker.run_once()["succeeded"] == 1
    assert worker.run_once()["succeeded"] == 0
    store.delete_memory(item.id)
    assert worker.run_once()["succeeded"] == 1
    assert index.indexed_state("1", item.id) == []


def test_newer_update_during_sync_is_not_acknowledged(setup):
    store, index = setup
    item = store.create_memory(user_id="1", memory_type="preference", content="Old preference")
    index.during = lambda: store.update_memory(item.id, content="New preference")
    worker = MemorySyncWorker(store, index)
    assert worker.run_once()["superseded"] == 1
    assert worker.run_once()["succeeded"] == 1
    assert index.indexed_state("1", item.id) == [fingerprint(store.get_memory(item.id))]


def test_reconcile_pages_all_rows_and_repairs_missing_duplicate_orphans(setup):
    store, index = setup
    items = [store.create_memory(user_id="1", memory_type="preference", content=f"Preference {i}") for i in range(5)]
    worker = MemorySyncWorker(store, index)
    worker.run_once()
    index.rows[("1", items[0].id)] = ["stale", "duplicate"]
    index.rows.pop(("1", items[-1].id))
    index.rows[("1", "999")] = ["orphan"]
    plan = worker.reconcile(page_size=2, dry_run=True)
    assert plan == {"scanned": 5, "repair": 2, "orphan": 1}
    assert ("1", "999") in index.rows
    worker.reconcile(page_size=2)
    assert ("1", "999") in index.rows  # scheduled repair never destroys unknown legacy orphans
    worker.reconcile(page_size=2, prune_orphans=True)
    worker.run_once()
    assert worker.reconcile(page_size=2) == {"scanned": 5, "repair": 0, "orphan": 0}


def test_lease_recovery_and_business_rollback(setup):
    store, index = setup
    with pytest.raises(RuntimeError):
        with store.engine.begin() as conn:
            enqueue(conn, "998", "1")
            raise RuntimeError("rollback")
    with store.engine.connect() as conn:
        assert conn.execute(select(jobs)).all() == []
    item = store.create_memory(user_id="1", memory_type="preference", content="Preference")
    with store.engine.begin() as conn:
        conn.execute(jobs.update().values(lease_until=time.time()+100, lease_token="crashed"))
    worker = MemorySyncWorker(store, index)
    assert worker.run_once()["succeeded"] == 0
    worker.clock = lambda: time.time()+101
    assert worker.run_once()["succeeded"] == 1
    assert index.indexed_state("1", item.id)


def test_projection_upsert_is_idempotent_and_removes_legacy_duplicates(setup, monkeypatch):
    from types import SimpleNamespace
    from petrochat.app.memory.mem0_adapter import Mem0MemoryAdapter
    from petrochat.app.core import llm

    store, _ = setup
    item = store.create_memory(user_id="1", memory_type="preference", content="Prefer concise answers")

    class Collection:
        def __init__(self):
            self.rows = {"legacy": {"user_id": "1", "petrochat_memory_id": item.id}}
            self.upserts = 0

        def get(self, **kwargs):
            return {"ids": list(self.rows), "metadatas": list(self.rows.values())}

        def upsert(self, ids, embeddings, metadatas):
            self.upserts += 1
            self.rows.update(zip(ids, metadatas))

        def delete(self, ids):
            for key in ids:
                self.rows.pop(key, None)

    collection = Collection()
    adapter = Mem0MemoryAdapter(SimpleNamespace(vector_store=SimpleNamespace(collection=collection)), enabled=True)
    monkeypatch.setattr(llm, "get_embedding", lambda: SimpleNamespace(embed_documents=lambda texts: [[1.0, 0.0]]))
    adapter.sync_current(item, user_id="1", memory_id=item.id)
    adapter.sync_current(item, user_id="1", memory_id=item.id)
    assert collection.upserts == 1 and len(collection.rows) == 1
    assert adapter.indexed_state("1", item.id) == [fingerprint(item)]
    store.delete_memory(item.id)
    adapter.sync_current(store.get_memory(item.id), user_id="1", memory_id=item.id)
    assert collection.rows == {}


def test_tenant_scoped_worker_leaves_other_jobs_untouched(setup):
    store, index = setup
    one = store.create_memory(user_id="1", memory_type="preference", content="Preference one")
    two = store.create_memory(user_id="2", memory_type="preference", content="Preference two")
    worker = MemorySyncWorker(store, index)
    assert worker.run_once(user_id="1")["succeeded"] == 1
    assert index.indexed_state("1", one.id)
    assert index.indexed_state("2", two.id) == []
    assert worker.reconcile(user_id="1") == {"scanned": 1, "repair": 0, "orphan": 0}
