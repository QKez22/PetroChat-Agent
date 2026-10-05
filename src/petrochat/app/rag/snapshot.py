"""离线快照的精确向量基准，不替换生产 Chroma；调用真实百炼 embedding。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from langchain_core.documents import Document

from ..core.config import get_settings
from ..core.llm import get_embedding
from .corpus import load_corpus


class SnapshotRetriever:
    def __init__(self, corpus_path: Path):
        self.chunks = load_corpus(corpus_path)
        payload = json.loads(corpus_path.read_text(encoding="utf-8"))
        s = get_settings()
        self.snapshot_id = payload["snapshot_id"]
        identity = hashlib.sha256(f"{self.snapshot_id}:{s.embedding_model}:{s.embedding_dim}:{s.dashscope_base_url}".encode()).hexdigest()
        cache = corpus_path.parent / f"vectors-{identity}.npz"
        self.embedder = get_embedding()
        if cache.exists():
            self.vectors = np.load(cache, allow_pickle=False)["vectors"]
        else:
            self.vectors = np.asarray(self.embedder.embed_documents([c.content for c in self.chunks]), dtype=np.float32)
            np.savez_compressed(cache, vectors=self.vectors)
        if self.vectors.shape != (len(self.chunks), s.embedding_dim):
            raise ValueError("embedding snapshot shape mismatch")
        self.vectors = self.vectors / np.maximum(np.linalg.norm(self.vectors, axis=1, keepdims=True), 1e-12)
        self.query_cache = corpus_path.parent / f"queries-{identity}.json"
        self.queries = json.loads(self.query_cache.read_text()) if self.query_cache.exists() else {}

    def invoke(self, question: str, top_k: int = 5, source: str | None = None) -> list[Document]:
        key = hashlib.sha256(question.encode()).hexdigest()
        if key not in self.queries:
            self.queries[key] = self.embedder.embed_query(question)
            self.query_cache.write_text(json.dumps(self.queries), encoding="utf-8")
        vector = np.asarray(self.queries[key], dtype=np.float32)
        scores = self.vectors @ (vector / max(np.linalg.norm(vector), 1e-12))
        if source:
            scores = np.where([c.source_doc == source for c in self.chunks], scores, -np.inf)
        indices = np.argsort(-scores, kind="stable")[:top_k]
        return [Document(page_content=self.chunks[i].content, metadata={
            **self.chunks[i].to_metadata(), "chunk_id": self.chunks[i].chunk_id,
            "score": float(1 - scores[i]), "backend": "snapshot_exact",
        }) for i in indices if np.isfinite(scores[i])]
