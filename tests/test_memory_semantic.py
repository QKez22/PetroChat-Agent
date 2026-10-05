from dataclasses import replace
from test_memory import make_memory_test_engine
from petrochat.app.memory.long_term import LongTermMemoryStore
from petrochat.app.memory.semantic import SemanticMemoryCache


class Embedder:
    def __init__(self):
        self.calls = 0
    def embed_documents(self, texts):
        self.calls += 1
        return [[1.,0.] if 'short' in t or 'concise' in t else [0.,1.] for t in texts]


def test_cache_is_scoped_versioned_bounded_and_semantic():
    store = LongTermMemoryStore(make_memory_test_engine())
    item = store.create_memory(user_id="1", memory_type="preference", content="Prefer concise responses")
    embedder, cache = Embedder(), SemanticMemoryCache(capacity=3)
    result, mode = cache.rank("1", "short answers", [item], embedder=embedder, model="v1")
    assert mode == "semantic" and result[0][0].id == item.id
    cache.rank("1", "short answers", [item], embedder=embedder, model="v1")
    assert embedder.calls == 1
    cache.rank("1", "short answers", [replace(item, content="Prefer long responses")], embedder=embedder, model="v1")
    assert embedder.calls == 2
    cache.rank("1", "short answers", [item], embedder=embedder, model="v2")
    assert embedder.calls == 3 and len(cache.cache) <= 3
    assert cache.rank("2", "short answers", [item], embedder=embedder)[0] == []


def test_failure_opens_circuit_and_offline_fallback_can_abstain():
    store = LongTermMemoryStore(make_memory_test_engine())
    item = store.create_memory(user_id="1", memory_type="preference", content="默认查看运行中的任务")
    class Broken:
        calls = 0
        def embed_documents(self, texts):
            self.calls += 1
            raise TimeoutError()
    embedder, cache = Broken(), SemanticMemoryCache()
    result, mode = cache.rank("1", "运行中任务", [item], embedder=embedder)
    assert mode == "lexical" and result
    assert cache.rank("1", "如何制作蛋糕", [item], embedder=embedder)[0] == []
    assert embedder.calls == 1


def test_candidate_extraction_isolated_and_cleanup_on_failure():
    from types import SimpleNamespace
    from petrochat.app.memory.mem0_adapter import Mem0MemoryAdapter
    class Client:
        def __init__(self):
            self.scopes, self.deleted = [], []
            self.vector_store = SimpleNamespace(collection=SimpleNamespace(delete=lambda **kw:self.deleted.append(kw)))
        def add(self, messages, **kwargs):
            self.scopes.append(kwargs["run_id"])
            raise TimeoutError()
    client = Client()
    adapter = Mem0MemoryAdapter(candidate_client=client,enabled=True)
    for _ in range(2):
        assert adapter.extract_candidates(messages=[{"role":"user","content":"Remember my preferences"}],user_id="1") == []
    assert client.scopes[0] != client.scopes[1]
    assert [r["where"]["run_id"] for r in client.deleted] == client.scopes


def test_short_explicit_preference_does_not_require_mem0(monkeypatch):
    from petrochat.app.memory.context import write_memory_candidates
    store = LongTermMemoryStore(make_memory_test_engine())
    result = write_memory_candidates(user_id="1",question="以后回答简洁",store=store)
    assert result and store.get_memory(result[0].id).metadata["value"] == "concise"


def test_expired_memory_never_uses_cached_vector_and_ttl_refreshes():
    store = LongTermMemoryStore(make_memory_test_engine())
    item = store.create_memory(user_id="1", memory_type="preference", content="Prefer concise responses")
    now = [0.0]
    cache, embedder = SemanticMemoryCache(ttl=10, clock=lambda: now[0]), Embedder()
    assert cache.rank("1", "short answers", [item], embedder=embedder)[0]
    expired = replace(item, expires_at="2000-01-01 00:00:00")
    assert cache.rank("1", "short answers", [expired], embedder=embedder)[0] == []
    now[0] = 11
    assert cache.rank("1", "short answers", [item], embedder=embedder)[0]
    assert embedder.calls == 2
