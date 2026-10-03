import pytest
from docx import Document

from petrochat.app.core.models import KnowledgeChunk
from petrochat.app.evaluation.golden_set import _rag_item_matches
from petrochat.app.rag.corpus import audit_labels, build_corpus, validate_cases


def test_snapshot_stable_and_unsupported_explicit(tmp_path):
    doc = Document()
    doc.add_paragraph("1.1 测试条款要求保留原文以及完整条件。")
    doc.save(tmp_path / "policy.docx")
    (tmp_path / "old.doc").write_bytes(b"legacy")
    first, second = build_corpus(tmp_path), build_corpus(tmp_path)
    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["excluded"] == [{"file": "old.doc", "reason": "unsupported_format"}]
    audit = audit_labels(first, [{"expected_source_file": "policy.docx", "expected_chunk_id": "待标注"}])
    assert audit["resolved"] == 0


def test_strict_evidence_matching_does_not_accept_substrings_or_body_spoof():
    row = {"expected_source_file": "policy.docx", "expected_section": "2.1"}
    assert _rag_item_matches(row, {"source_doc": "policy", "section_number": "2.1"})
    assert not _rag_item_matches(row, {"source_doc": "policy", "section_number": "12.1"})
    assert not _rag_item_matches(row, {"content": "policy.docx 2.1"})


def test_benchmark_rejects_invented_quote():
    chunk = KnowledgeChunk(chunk_id="a", source_doc="policy", content="真实条件")
    with pytest.raises(ValueError, match="unverified"):
        validate_cases([{"id": "q", "question": "条件？", "evidence": [{"chunk_id": "a", "quote": "虚构"}]}], [chunk])
