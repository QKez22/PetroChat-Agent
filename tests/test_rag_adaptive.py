from types import SimpleNamespace

from langchain_core.documents import Document

from petrochat.app.rag import adaptive, hybrid, retriever


def doc(key, source="甲公司设备管理细则", content="设备规则", path=""):
    return Document(
        page_content=content, metadata={"chunk_id": key, "source_doc": source, "section_path": path}
    )


def test_explicit_title_is_unique_and_not_model_authority():
    a, b = doc("a"), doc("b", "乙公司采购管理规范")
    assert adaptive.explicit_source("设备管理细则适用于哪些部门？", [a, b]) == (
        "甲公司设备管理细则",
        "适用于哪些部门",
    )
    assert adaptive.explicit_source("对比设备管理细则与采购管理规范", [a, b])[0] is None
    assert (
        adaptive.explicit_source("设备管理细则怎么执行？", [a, doc("c", "乙公司设备管理细则")])[0]
        is None
    )
    assert adaptive.explicit_source("设备管理细则怎么执行？", [b])[0] is None


def test_parent_text_avoids_repeating_clause_body():
    d = doc("a", content="2.1 应执行设备检查", path="2 职责 > 2.1 应执行设备检查")
    text = adaptive.contextual_text(d)
    assert text.count("应执行设备检查") == 1 and "2 职责" in text and "甲公司" in text
    assert "适用" in adaptive.search_tokens("适用范围")


def test_agreement_skips_reranker(monkeypatch):
    d = doc("a")
    monkeypatch.setattr(adaptive, "lexical_search", lambda *a: [d])
    monkeypatch.setattr(
        adaptive, "rerank", lambda *a, **kw: (_ for _ in ()).throw(AssertionError())
    )
    result = adaptive.adaptive_search("q", [d], lambda *a: [d])
    assert result[0].metadata["rerank_status"] == "skipped:agreement"


def test_disagreement_gets_contextual_rerank(monkeypatch):
    a, b = doc("a"), doc("b")
    monkeypatch.setattr(adaptive, "lexical_search", lambda *args: [b])
    calls = []

    def rank(q, docs, k, **kw):
        calls.append(kw)
        return [b]

    monkeypatch.setattr(adaptive, "rerank", rank)
    assert adaptive.adaptive_search("q", [a, b], lambda *args: [a])[0].metadata["chunk_id"] == "b"
    assert calls == [{"contextual": True}]


def test_production_source_filter_intersects_existing_acl(monkeypatch):
    seen = []

    def chunks(**kwargs):
        return [
            SimpleNamespace(
                content="规则", chunk_id="a", metadata={"source_doc": "甲公司设备管理细则"}
            )
        ]

    def query(**kwargs):
        seen.append(kwargs)
        return [
            SimpleNamespace(
                content="规则",
                chunk_id="a",
                score=0.1,
                metadata={"source_doc": "甲公司设备管理细则"},
            )
        ]

    monkeypatch.setattr(retriever, "get_chunks", chunks)
    monkeypatch.setattr(retriever, "_vector_query", query)
    monkeypatch.setattr(adaptive, "lexical_search", lambda q, ds, k: ds)
    retriever.make_retriever(mode="adaptive_hybrid", where={"version_id": "allowed"}).invoke(
        "设备管理细则适用于哪些部门？"
    )
    assert seen[0]["where"] == {
        "$and": [{"version_id": "allowed"}, {"source_doc": "甲公司设备管理细则"}]
    }


def test_contextual_rerank_preserves_original_evidence(monkeypatch):
    seen = []

    def post(*args, **kw):
        seen.append(kw["json"]["input"]["documents"][0])
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"output": {"results": [{"index": 0, "relevance_score": 0.9}]}},
        )

    monkeypatch.setattr(hybrid.httpx, "post", post)
    d = doc("a")
    result = hybrid.rerank("q", [d], contextual=True)
    assert result[0].page_content == d.page_content
    assert "文档：甲公司设备管理细则" in seen[0]
