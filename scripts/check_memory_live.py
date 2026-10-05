"""Explicit live smoke: unique tenant + collection; only owned fixtures are removed."""
import argparse
import json
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import text

from petrochat.app.core import get_settings
from petrochat.app.memory.long_term import LongTermMemoryStore
from petrochat.app.memory.mem0_adapter import Mem0MemoryAdapter, _build_mem0_client
from petrochat.app.memory.sync import MemorySyncWorker, fingerprint
from petrochat.app.rag.vector_store import get_client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    if not parser.parse_args().execute:
        raise SystemExit("Use --execute to create and clean isolated test fixtures (uses embedding API).")
    settings = get_settings()
    settings.memory_sync_enabled = True
    run = uuid.uuid4().hex
    user_id = str(int(run[:14], 16))
    name = "memory_smoke_" + run
    store = LongTermMemoryStore()
    owned = []
    client = get_client()
    with store.engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM user_memory WHERE user_id=:u"), {"u": user_id}).scalar() == 0
    with tempfile.TemporaryDirectory(prefix="petrochat-memory-smoke-") as temporary:
        settings.mem0_history_db_path = Path(temporary) / "history.db"
        adapter = None
        try:
            adapter = Mem0MemoryAdapter(_build_mem0_client(name), enabled=True)
            worker = MemorySyncWorker(store, adapter)
            item = store.create_memory(user_id=user_id, memory_type="preference",
                content="用户希望回答简洁，优先使用中文。", source="test:" + run)
            owned.append(item.id)
            assert worker.run_once(user_id=user_id)["succeeded"] == 1
            assert adapter.indexed_state(user_id, item.id) == [fingerprint(store.get_memory(item.id))]
            assert worker.run_once(user_id=user_id)["succeeded"] == 0
            assert adapter.search(user_id=user_id, query="用户偏好怎样的回答语言和长度", limit=3)
            store.update_memory(item.id, content="用户希望详细回答，优先使用中文。")
            assert worker.run_once(user_id=user_id)["succeeded"] == 1
            adapter.remove_index_key(user_id, item.id)
            assert worker.reconcile(page_size=1, user_id=user_id)["repair"] == 1
            assert worker.run_once(user_id=user_id)["succeeded"] == 1
            store.delete_memory(item.id)
            assert worker.run_once(user_id=user_id)["succeeded"] == 1
            assert adapter.indexed_state(user_id, item.id) == []
            assert worker.reconcile(page_size=1, user_id=user_id)["repair"] == 0
            print(json.dumps({"mysql_crud": True, "chroma_search": True,
                "idempotent": True, "update": True, "repair": True, "delete": True}))
        finally:
            # Verify exact ownership before physical removal. Never touch real tenants.
            with store.engine.begin() as conn:
                for memory_id in owned:
                    source = conn.execute(text("SELECT source FROM user_memory WHERE id=:id AND user_id=:u"),
                        {"id": memory_id, "u": user_id}).scalar()
                    assert source == "test:" + run
                    for table in ("agent_memory_sync", "memory_event"):
                        conn.execute(text(f"DELETE FROM {table} WHERE memory_id=:id AND user_id=:u"), {"id": memory_id, "u": user_id})
                    conn.execute(text("DELETE FROM user_memory WHERE id=:id AND user_id=:u"), {"id": memory_id, "u": user_id})
            if adapter is not None:
                adapter.active_client.db.close()
            if name in [str(c) if isinstance(c, str) else c.name for c in client.list_collections()]:
                client.delete_collection(name)
            print("Owned smoke fixtures cleaned.")


if __name__ == "__main__":
    main()
