"""可复现的本地语料快照；原文件和私有标注只写入 ignored 数据目录。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..core.models import KnowledgeChunk
from .parser import parse_docx


def source_key(value: str) -> str:
    """统一标注文件名与检索 metadata；不删除版本信息。"""
    return Path(value.replace("\\", "/")).stem.casefold().strip()


def build_corpus(raw_dir: Path) -> dict:
    records, documents, excluded = [], [], []
    for path in sorted(raw_dir.iterdir()):
        if not path.is_file() or path.name.startswith(("~$", ".")):
            continue
        if path.suffix.lower() != ".docx":
            excluded.append({"file": path.name, "reason": "unsupported_format"})
            continue
        chunks = parse_docx(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        documents.append({"file": path.name, "sha256": digest, "chunks": len(chunks)})
        for chunk in chunks:
            row = chunk.model_dump(mode="json")
            # 导入时间不是内容身份，避免相同输入生成不同快照。
            row.pop("created_at", None)
            records.append(row)
    payload = {"parser_version": "docx-v1", "documents": documents, "chunks": records}
    snapshot = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return {**payload, "snapshot_id": snapshot, "excluded": excluded}


def load_corpus(path: Path) -> list[KnowledgeChunk]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [KnowledgeChunk.model_validate(row) for row in payload["chunks"]]


def audit_labels(corpus: dict, labels: list[dict]) -> dict:
    """仅承认实际 ID 或精确条款号；关键词候选绝不自动升格为真值。"""
    by_id = {c["chunk_id"]: c for c in corpus["chunks"]}
    sources = {source_key(c["source_doc"]) for c in corpus["chunks"]}
    results = []
    for row in labels:
        expected = row.get("expected_chunk_id", "").strip()
        source = source_key(row.get("expected_source_file", ""))
        chunk = by_id.get(expected)
        if source not in sources:
            reason = "source_unavailable"
        elif not chunk:
            reason = "unresolved_evidence_id"
        elif source_key(chunk["source_doc"]) != source:
            reason = "source_mismatch"
        elif row.get("expected_section") and row["expected_section"] != chunk["section_number"]:
            reason = "section_mismatch"
        else:
            reason = "resolved"
        results.append({
            "dialogue_id": row.get("dialogue_id"), "turn_id": row.get("turn_id"),
            "status": reason, "expected_chunk_id": expected,
        })
    return {"snapshot_id": corpus["snapshot_id"], "total": len(results),
            "resolved": sum(r["status"] == "resolved" for r in results), "rows": results}


def validate_cases(cases: list[dict], chunks: list[KnowledgeChunk]) -> None:
    """独立检索基准必须携带可核对原文，阻止失效/占位标注参与评分。"""
    by_id = {c.chunk_id: c for c in chunks}
    seen = set()
    for case in cases:
        if case["id"] in seen:
            raise ValueError("duplicate case id")
        seen.add(case["id"])
        if not case.get("question", "").strip() or not case.get("evidence"):
            raise ValueError("question and reviewed evidence required")
        for evidence in case["evidence"]:
            chunk = by_id.get(evidence["chunk_id"])
            quote = evidence.get("quote", "").strip()
            if chunk is None or not quote or quote not in chunk.content:
                raise ValueError(f"unverified evidence: {case['id']}")
