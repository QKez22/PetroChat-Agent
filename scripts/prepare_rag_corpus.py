"""构建语料和标注审计报告，不修改原始语料和 Golden Set。"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from petrochat.app.rag.corpus import audit_labels, build_corpus


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--golden-dir", type=Path)
    parser.add_argument("--out", type=Path, default=Path("data/runtime/rag"))
    args = parser.parse_args()
    corpus = build_corpus(args.raw_dir)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "corpus.json").write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = {"snapshot_id": corpus["snapshot_id"], "documents": len(corpus["documents"]),
               "chunks": len(corpus["chunks"]), "excluded": len(corpus["excluded"])}
    if args.golden_dir:
        with (args.golden_dir / "golden_rag_evidence.csv").open(encoding="utf-8-sig", newline="") as f:
            report = audit_labels(corpus, list(csv.DictReader(f)))
        (args.out / "label_audit.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary.update(labels=report["total"], resolved=report["resolved"])
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
