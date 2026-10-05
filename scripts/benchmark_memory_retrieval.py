"""Synthetic frozen memory retrieval; optional component-only Chroma comparison.

No private user memories read. Embedding cost is reported separately from warm
retrieval. Never label these small developer-authored cases production accuracy.
"""
import argparse
import hashlib
import json
import statistics
import time
import uuid
from pathlib import Path

from petrochat.app.core.llm import get_embedding
from petrochat.app.memory.context import _memory_score
from petrochat.app.memory.long_term import MemoryItem
from petrochat.app.memory.semantic import SemanticMemoryCache, lexical_score
from petrochat.app.rag.vector_store import get_client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--components", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("Requires --execute (embedding API and optional isolated Chroma collection)")
    fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/memory_retrieval.json"
    raw = fixture.read_bytes()
    data = json.loads(raw)
    cases = [r for r in data["cases"] if r["split"] == args.split]
    items = [MemoryItem(id=r["id"], user_id="benchmark", memory_type="preference", content=r["content"],
        source="synthetic", confidence=1.0, status="active", metadata={}, created_at="2026-01-01", updated_at="2026-01-01") for r in data["memories"]]
    cache = SemanticMemoryCache()
    start = time.perf_counter()
    vectors = cache.vectors("benchmark", [(i.id,i.content) for i in items] + [("query",r["query"]) for r in cases])
    embedding_ms = (time.perf_counter()-start)*1000
    results = []
    for case in cases:
        legacy = sorted(items, key=lambda i: _memory_score(i,case["query"]), reverse=True)[0].id
        lexical = sorted([(i.id,lexical_score(i.content,case["query"])) for i in items], key=lambda r:r[1], reverse=True)
        semantic, mode = cache.rank("benchmark",case["query"],items,threshold=args.threshold)
        assert mode == "semantic", "do not report fallback as semantic success"
        results.append({**case,"legacy":legacy,"lexical":lexical[0][0] if lexical[0][1]>0 else None,
            "semantic":semantic[0][0].id if semantic else None,"top_score":semantic[0][1] if semantic else None})
    summary = {}
    for mode in ("legacy","lexical","semantic"):
        positives = [r for r in results if r["expected"] is not None]
        negatives = [r for r in results if r["expected"] is None]
        summary[mode] = {"hit_at_1":sum(r[mode]==r["expected"] for r in positives)/len(positives),
            "unrelated_injection_rate":sum(r[mode] is not None for r in negatives)/len(negatives)}
    report = {"fixture_sha256":hashlib.sha256(raw).hexdigest(),"split":args.split,"threshold":args.threshold,
        "positive_cases":len(positives),"negative_cases":len(negatives),"embedding_batch_ms":embedding_ms,
        "summary":summary,"results":results}
    if args.components:
        client = get_client()
        name = "memory_bench_" + uuid.uuid4().hex
        collection = client.create_collection(name, metadata={"hnsw:space":"cosine"})
        try:
            measurements = {}
            for size in (8,200):
                docs = [list(vectors[i%len(items)]) for i in range(size)]
                ids = [str(i) for i in range(size)]
                collection.upsert(ids=ids,embeddings=docs)
                local, remote = [], []
                for _ in range(5):
                    for query in vectors[len(items):]:
                        start = time.perf_counter()
                        sorted((sum(a*b for a,b in zip(query,v)) for v in docs), reverse=True)[:5]
                        local.append((time.perf_counter()-start)*1000)
                        start = time.perf_counter()
                        collection.query(query_embeddings=[list(query)],n_results=5,include=["distances"])
                        remote.append((time.perf_counter()-start)*1000)
                def stats(values):
                    return {"p50_ms":statistics.median(values),"p95_ms":sorted(values)[int(.95*(len(values)-1))]}
                measurements[str(size)]={"samples":len(local),"python_exact_cosine":stats(local),"chroma_http":stats(remote)}
            report["component_only_no_embedding_or_mysql"] = measurements
        finally:
            client.delete_collection(name)
    output = Path("data/runtime/memory")
    output.mkdir(parents=True,exist_ok=True)
    (output / f"retrieval_{args.split}.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
