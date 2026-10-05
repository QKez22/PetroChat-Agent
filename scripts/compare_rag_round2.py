"""冻结题集上的配对实测：轮换调用顺序，保留所有结果，不按成绩改标签。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from petrochat.app.evaluation.rag_benchmark import benchmark
from petrochat.app.rag import make_retriever
from petrochat.app.rag.corpus import load_corpus, validate_cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=Path("data/runtime/rag/corpus.json"))
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--cases-sha256", required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--output", type=Path, default=Path("data/runtime/rag/round2_paired.json"))
    args = parser.parse_args()
    if args.repeats < 1 or args.repeats > 5:
        parser.error("repeats must be 1..5")
    cases_text = args.cases.read_text(encoding="utf-8")
    digest = hashlib.sha256(cases_text.encode()).hexdigest()
    if digest != args.cases_sha256:
        parser.error("frozen cases hash mismatch")
    cases = json.loads(cases_text)
    validate_cases(cases, load_corpus(args.corpus))
    payload = json.loads(args.corpus.read_text(encoding="utf-8"))
    modes = ["vector", "hybrid_rerank", "adaptive_hybrid"]
    retrievers = {m: make_retriever(mode=m, collection=args.collection) for m in modes}
    rows = {m: [] for m in modes}
    # 固定旧开发题暖机，不纳入质量和耗时统计。
    for retriever in retrievers.values():
        retriever.invoke("什么是修旧利废？")
    for repeat in range(args.repeats):
        for index, case in enumerate(cases):
            offset = (repeat + index) % len(modes)
            for mode in modes[offset:] + modes[:offset]:
                report = benchmark(
                    [case], retrievers[mode].invoke, mode=mode, snapshot_id=payload["snapshot_id"]
                )
                rows[mode].append({**report["rows"][0], "repeat": repeat})
            print(
                json.dumps(
                    {"repeat": repeat + 1, "completed_cases": index + 1, "total_cases": len(cases)}
                ),
                flush=True,
            )
    summaries = {}
    for mode, items in rows.items():
        summaries[mode] = {
            "recall_at_5": float(np.mean([r["recall_at_5"] for r in items])),
            "mrr_at_5": float(np.mean([r["rr"] for r in items])),
            "p50_ms": float(np.percentile([r["latency_ms"] for r in items], 50)),
            "p95_ms": float(np.percentile([r["latency_ms"] for r in items], 95)),
            "rerank_skipped": sum(r["rerank_skipped"] for r in items),
            "rerank_fallbacks": sum(r["rerank_fallback"] for r in items),
        }
    paired = {}
    for baseline in modes[:2]:
        paired[baseline] = {}
        for metric in ["recall_at_5", "rr"]:
            # 同一道题重复运行先平均，不能把重复当作独立的新样本。
            deltas = np.asarray(
                [
                    np.mean([r[metric] for r in rows["adaptive_hybrid"] if r["id"] == c["id"]])
                    - np.mean([r[metric] for r in rows[baseline] if r["id"] == c["id"]])
                    for c in cases
                ]
            )
            rng = np.random.default_rng(42)
            bootstrap = np.mean(rng.choice(deltas, size=(5000, len(deltas)), replace=True), axis=1)
            paired[baseline][metric] = {
                "mean_delta": float(deltas.mean()),
                "bootstrap_95_interval": np.percentile(bootstrap, [2.5, 97.5]).tolist(),
            }
    code_files = [
        "src/petrochat/app/rag/adaptive.py",
        "src/petrochat/app/rag/hybrid.py",
        "src/petrochat/app/rag/retriever.py",
    ]
    result = {
        "case_count": len(cases),
        "repeats": args.repeats,
        "cases_sha256": digest,
        "corpus_snapshot_id": payload["snapshot_id"],
        "collection": args.collection,
        "query_embedding_cache_enabled": False,
        "code_sha256": hashlib.sha256(
            b"".join(Path(p).read_bytes() for p in code_files)
        ).hexdigest(),
        "summaries": summaries,
        "paired_delta": paired,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}), flush=True)


if __name__ == "__main__":
    main()
