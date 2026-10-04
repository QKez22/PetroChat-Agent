from datetime import date
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from sqlalchemy import create_engine

from petrochat.app.core.models import KnowledgeChunk
from petrochat.app.rag import catalog as module
from petrochat.app.rag.catalog import Catalog, PolicyError, VersionPolicy, select_versions


def policy(version="old", **kw):
    return VersionPolicy(
        source_doc=version,
        document_id="standard",
        version_id=version,
        allowed_users=["alice"],
        **kw,
    )


def test_half_open_historical_versions():
    old = policy(effective_from=date(2020, 1, 1), effective_to=date(2024, 1, 1), status="verified")
    new = policy("new", effective_from=date(2024, 1, 1), status="verified")
    assert select_versions([old, new], "alice", date(2023, 12, 31)) == [old]
    assert select_versions([old, new], "alice", date(2024, 1, 1)) == [new]
    assert select_versions([old, new], "bob", date(2024, 1, 1)) == []


def test_unknown_not_valid_for_historical_claims():
    unknown = policy()
    assert select_versions([unknown], "alice", None) == [unknown]
    assert select_versions([unknown], "alice", date.today()) == []
    assert select_versions([unknown], "", None) == []
    with pytest.raises(PolicyError):
        select_versions([unknown, policy("new")], "alice", None)


def test_invalid_interval():
    with pytest.raises(ValueError):
        policy(status="verified")
    with pytest.raises(ValueError):
        policy(effective_from=date(2024, 1, 1), effective_to=date(2024, 1, 1))


def test_manifest_immutable_and_atomic():
    cat = Catalog(create_engine("sqlite://"))
    cat.initialize()
    cat.publish("one", "collection_one", {"versions": []})
    with pytest.raises(ValueError):
        cat.publish("one", "changed", {"versions": []})
    assert cat.current()["collection_name"] == "collection_one"
    cat.publish("two", "collection_two", {"versions": []})
    assert cat.current()["snapshot_id"] == "two"


def test_scoped_query_pins_manifest_and_denies_override(monkeypatch):
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(rag_catalog_enabled=True))
    calls = []

    def current(self):
        calls.append(1)
        return {
            "collection_name": "immutable",
            "payload": {"versions": [policy().model_dump(mode="json")]},
        }

    monkeypatch.setattr(Catalog, "current", current)
    monkeypatch.setattr(module, "get_app_engine", lambda: None)
    with pytest.raises(PolicyError):
        module.scoped_query()
    with module.request_scope("alice"):
        where, name = module.scoped_query({"source_doc": "old"})
        assert name == "immutable"
        assert where["$and"][0] == {"version_id": {"$in": ["old"]}}
        module.scoped_query()
        with pytest.raises(PolicyError):
            module.scoped_query(collection_name="bypass")
    assert len(calls) == 1


def test_build_failure_does_not_publish():
    cat = Catalog(create_engine("sqlite://"))
    cat.initialize()
    cat.publish("old", "old_collection", {})
    collection = SimpleNamespace(upsert=lambda **kw: None, count=lambda: 0)
    client = SimpleNamespace(create_collection=lambda *a, **kw: collection)
    with pytest.raises(ValueError, match="条数"):
        module.build_snapshot(
            [KnowledgeChunk(chunk_id="a", content="text", source_doc="old")],
            [policy()],
            catalog=cat,
            client=client,
            embedder=SimpleNamespace(embed_documents=lambda texts: [[1.0, 0.0]]),
        )
    assert cat.current()["snapshot_id"] == "old"


def test_reference_one_hop_and_same_version(monkeypatch):
    from petrochat.app.rag import vector_store

    seen = []

    def get(**kw):
        seen.append(kw)
        return [
            SimpleNamespace(
                chunk_id="target", content="按第3.1条执行", metadata={"version_id": "v"}
            )
        ]

    monkeypatch.setattr(vector_store, "get_chunks", get)
    docs = [
        Document(page_content="按第2.1条执行", metadata={"chunk_id": "source", "version_id": "v"})
    ]
    assert len(module.expand_references(docs)) == 2
    assert len(seen) == 1
    assert seen[0]["where"]["$and"][0] == {"version_id": "v"}
    with pytest.raises(PolicyError):
        module.expand_references(docs, max_extra=0)
