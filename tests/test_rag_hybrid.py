from types import SimpleNamespace

import httpx
from langchain_core.documents import Document

from petrochat.app.rag import hybrid, retriever


def doc(key, text="设备管理"):
    return Document(page_content=text, metadata={"chunk_id": key})


def test_tokenize_preserves_clause_and_acronym():
    assert {"itpm", "2.1.3"} <= set(hybrid.tokenize("ITPM 第2.1.3条"))


def test_bm25_rare_term():
    docs = [doc("a", "ITPM 检测策略"), doc("b", "物料采购"), doc("c", "仓库盘点")]
    assert hybrid.keyword_search("ITPM", docs)[0].metadata["chunk_id"] == "a"


def test_rrf_deduplicates_each_route():
    a, b = doc("a"), doc("b")
    result = hybrid.fuse([a, a, b], [b, a])
    assert len(result) == 2
    assert result[0].metadata["chunk_id"] == "a"
    assert result[0].metadata["rrf_score"] == 1 / 61 + 1 / 62


def test_rerank_validates_indices(monkeypatch):
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"output": {"results": [{"index": 20, "relevance_score": 1}]}},
    )
    monkeypatch.setattr(hybrid.httpx, "post", lambda *a, **kw: response)
    result = hybrid.rerank("q", [doc("a")])
    assert result[0].metadata["rerank_status"] == "fallback:ValueError"


def test_rerank_timeout_is_explicit(monkeypatch):
    def fail(*a, **kw):
        raise httpx.ReadTimeout("private request details")

    monkeypatch.setattr(hybrid.httpx, "post", fail)
    result = hybrid.rerank("q", [doc("a")])
    assert result[0].metadata["rerank_status"] == "fallback:ReadTimeout"


def test_rerank_success(monkeypatch):
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"output": {"results": [{"index": 1, "relevance_score": 0.9}]}},
    )
    monkeypatch.setattr(hybrid.httpx, "post", lambda *a, **kw: response)
    assert hybrid.rerank("q", [doc("a"), doc("b")], 1)[0].metadata["chunk_id"] == "b"


def test_hybrid_scopes_both_routes(monkeypatch):
    seen = []

    def vector(**kw):
        seen.append(kw["where"])
        return [
            SimpleNamespace(
                content="ITPM", chunk_id="a", score=0.2, metadata={"source_doc": "allowed"}
            )
        ]

    def corpus(**kw):
        seen.append(kw["where"])
        return vector(**kw)

    monkeypatch.setattr(retriever, "_vector_query", vector)
    monkeypatch.setattr(retriever, "get_chunks", corpus)
    result = retriever.make_retriever(mode="hybrid", where={"source_doc": "allowed"}).invoke("ITPM")
    assert result[0].metadata["chunk_id"] == "a"
    assert all(w == {"source_doc": "allowed"} for w in seen)
