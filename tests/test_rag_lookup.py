from types import SimpleNamespace
from importlib import import_module

from langchain_core.documents import Document

from petrochat.app.evaluation.rag_benchmark import benchmark

lookup = import_module("petrochat.app.tools.lookup")


def test_exact_lookup_never_embeds_and_keeps_all_chunks(monkeypatch):
    monkeypatch.setattr(lookup, "resolve_sources", lambda h: ["policy"])
    seen = []
    def get(where):
        seen.append(where)
        return [SimpleNamespace(chunk_id=f"c{i}", content=f"part{i}", metadata={"source_doc": "policy", "section_number": "2.1"}) for i in range(8)]
    monkeypatch.setattr(lookup, "get_chunks", get)
    monkeypatch.setattr(lookup, "make_retriever", lambda **kw: (_ for _ in ()).throw(AssertionError()))
    result = lookup.lookup_section.invoke({"source_doc_hint": "policy", "section_number": "2.1"})
    assert "part7" in result
    assert seen[0]["$and"][1] == {"source_doc": {"$in": ["policy"]}}


def test_document_filter_is_applied_before_topk(monkeypatch):
    monkeypatch.setattr(lookup, "resolve_sources", lambda h: ["policy"])
    seen = []
    def query(**kw):
        seen.append(kw)
        return SimpleNamespace(invoke=lambda q: [])
    monkeypatch.setattr(lookup, "make_retriever", query)
    lookup.search_within_doc.invoke({"query": "q", "source_doc_hint": "policy", "top_k": 5})
    assert seen[0]["where"] == {"source_doc": {"$in": ["policy"]}}
    assert seen[0]["top_k"] == 5


def test_benchmark_requires_complete_multi_evidence():
    cases = [{"id": "q", "question": "q", "evidence": [{"chunk_id": "a"}, {"chunk_id": "b"}]}]
    report = benchmark(cases, lambda q: [Document(page_content="", metadata={"chunk_id": "a"})], mode="fixture", snapshot_id="s")
    assert report["recall_at_5"] == 0.5
    assert report["complete_evidence_rate"] == 0
