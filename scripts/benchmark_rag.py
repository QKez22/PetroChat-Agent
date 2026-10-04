"""先校验原文真值，再调用真实检索器生成基线，失败不生成成功报告。"""

import argparse
import json
from pathlib import Path

from petrochat.app.evaluation.rag_benchmark import benchmark
from petrochat.app.rag import make_retriever
from petrochat.app.rag.corpus import load_corpus, validate_cases


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", type=Path, default=Path("data/runtime/rag/corpus.json"))
    p.add_argument("--cases", type=Path, default=Path("data/runtime/rag/reviewed_cases.json"))
    p.add_argument("--split", choices=["dev", "test"], default="dev")
    p.add_argument("--output", type=Path, default=Path("data/runtime/rag/vector_baseline.json"))
    p.add_argument("--collection")
    p.add_argument(
        "--mode", choices=["vector", "bm25", "hybrid", "hybrid_rerank"], default="vector"
    )
    p.add_argument("--backend", choices=["chroma", "snapshot"], default="chroma")
    args = p.parse_args()
    cases = [
        c for c in json.loads(args.cases.read_text(encoding="utf-8")) if c["split"] == args.split
    ]
    validate_cases(cases, load_corpus(args.corpus))
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    if args.backend == "snapshot":
        from petrochat.app.rag.snapshot import SnapshotRetriever

        retriever = SnapshotRetriever(args.corpus)
        from langchain_core.documents import Document
        from petrochat.app.rag.hybrid import keyword_search, fuse, rerank

        documents = [
            Document(page_content=c.content, metadata={**c.to_metadata(), "chunk_id": c.chunk_id})
            for c in retriever.chunks
        ]

        def retrieve(question):
            if args.mode == "vector":
                return retriever.invoke(question)
            lexical = keyword_search(question, documents, 30)
            if args.mode == "bm25":
                return lexical[:5]
            candidates = fuse(retriever.invoke(question, 30), lexical, k=30)
            return rerank(question, candidates) if args.mode == "hybrid_rerank" else candidates[:5]
    else:
        if args.mode == "bm25":
            p.error("bm25 ablation requires snapshot backend")
        retriever = make_retriever(top_k=5, collection=args.collection, mode=args.mode)
        retrieve = retriever.invoke
    result = benchmark(
        cases, retrieve, mode=f"{args.backend}_{args.mode}", snapshot_id=corpus["snapshot_id"]
    )
    result["query_embedding_cache_enabled"] = args.backend == "snapshot"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}))


if __name__ == "__main__":
    main()
