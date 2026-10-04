"""使用已核对证据的真实检索评测；与 oracle 管道分离。"""
from __future__ import annotations

import time
from statistics import mean

import numpy as np


def benchmark(cases, retrieve, *, mode: str, snapshot_id: str) -> dict:
    rows = []
    for case in cases:
        started = time.perf_counter()
        docs = retrieve(case["question"])
        latency = (time.perf_counter() - started) * 1000
        ids = list(dict.fromkeys(d.metadata["chunk_id"] for d in docs))
        expected = {e["chunk_id"] for e in case["evidence"]}
        hits = expected.intersection(ids[:5])
        ranks = [ids.index(cid) + 1 for cid in expected.intersection(ids)]
        rows.append({"id": case["id"], "retrieved_ids": ids, "latency_ms": round(latency, 2),
                     "rerank_fallback": any(str(d.metadata.get("rerank_status", "")).startswith("fallback:") for d in docs),
                     "recall_at_5": len(hits) / len(expected), "complete": expected <= set(ids[:5]),
                     "rr": 1 / min(ranks) if ranks else 0})
    return {"mode": mode, "snapshot_id": snapshot_id, "case_count": len(rows),
            "rerank_fallback_count": sum(r["rerank_fallback"] for r in rows),
            "recall_at_5": mean(r["recall_at_5"] for r in rows) if rows else None,
            "complete_evidence_rate": mean(r["complete"] for r in rows) if rows else None,
            "mrr": mean(r["rr"] for r in rows) if rows else None,
            "p95_ms": float(np.percentile([r["latency_ms"] for r in rows], 95)) if rows else None,
            "rows": rows}
