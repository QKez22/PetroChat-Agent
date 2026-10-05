"""逐阶段检查旧回归集，记录候选丢失位置；原始结果只能写私有目录。"""

import argparse
import json
from pathlib import Path

from langchain_core.documents import Document

from petrochat.app.rag.hybrid import fuse, keyword_search, rerank
from petrochat.app.rag.snapshot import SnapshotRetriever


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=Path("data/runtime/rag/corpus.json"))
    parser.add_argument("--cases", type=Path, default=Path("data/runtime/rag/reviewed_cases.json"))
    parser.add_argument(
        "--output", type=Path, default=Path("data/runtime/rag/round2_diagnosis.json")
    )
    args = parser.parse_args()
    retriever = SnapshotRetriever(args.corpus)
    corpus = [
        Document(page_content=c.content, metadata={**c.to_metadata(), "chunk_id": c.chunk_id})
        for c in retriever.chunks
    ]
    rows = []
    for case in json.loads(args.cases.read_text(encoding="utf-8")):
        if case["split"] != "test":
            continue
        vector = retriever.invoke(case["question"], len(corpus))
        lexical = keyword_search(case["question"], corpus, len(corpus))
        merged = fuse(vector[:30], lexical[:30], k=30)
        ranked = rerank(case["question"], merged, len(merged))
        stages = {"vector": vector, "bm25": lexical, "rrf30": merged, "rerank": ranked}
        ranks = {}
        for name, docs in stages.items():
            ids = [d.metadata["chunk_id"] for d in docs]
            ranks[name] = {
                e["chunk_id"]: ids.index(e["chunk_id"]) + 1 if e["chunk_id"] in ids else None
                for e in case["evidence"]
            }
        rows.append(
            {
                "id": case["id"],
                "question": case["question"],
                "ranks": ranks,
                "top3": {
                    name: [
                        {"id": d.metadata["chunk_id"], "content": d.page_content} for d in docs[:3]
                    ]
                    for name, docs in stages.items()
                },
            }
        )
        print(
            json.dumps(
                {
                    "id": case["id"],
                    "ranks": {name: list(values.values()) for name, values in ranks.items()},
                }
            ),
            flush=True,
        )
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
