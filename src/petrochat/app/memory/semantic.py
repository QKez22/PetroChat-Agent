"""Bounded tenant/version/model-scoped embedding cache with offline fallback."""
from __future__ import annotations

import hashlib
import math
import re
import threading
import time
from collections import OrderedDict
from functools import lru_cache

from ..core import get_settings
from .validity import is_effective


def lexical_score(content: str, query: str) -> float:
    import jieba
    stops = {"用户", "默认", "希望", "喜欢", "偏好", "什么", "怎样", "怎么", "一下", "我的", "可以", "需要", "应该", "采用", "优先"}
    def tokens(value):
        return {w.lower() for w in jieba.cut_for_search(value) if len(w.strip()) > 1 and w not in stops and re.search(r"\w", w)}
    a, b = tokens(content), tokens(query)
    return len(a & b) / max(1, len(b))


def unit_vector(values):
    if not values or not all(math.isfinite(v) for v in values):
        raise ValueError("invalid embedding")
    length = math.sqrt(sum(v*v for v in values))
    if length == 0:
        raise ValueError("zero embedding")
    return tuple(v / length for v in values)


class SemanticMemoryCache:
    def __init__(self, capacity=4096, ttl=3600, clock=time.monotonic):
        self.capacity, self.ttl, self.clock = capacity, ttl, clock
        self.cache = OrderedDict()
        self.lock = threading.RLock()
        self.blocked_until = 0.0

    def unavailable(self):
        with self.lock:
            self.blocked_until = self.clock() + 60

    def vectors(self, user_id: str, entries: list[tuple[str, str]], *, embedder=None, model=None):
        s = get_settings()
        model = model or f"{s.dashscope_base_url}/{s.embedding_model}/{s.embedding_dim}"
        keys = [(user_id, identity, hashlib.sha256(content.encode()).hexdigest(), model) for identity, content in entries]
        with self.lock:
            found, missing = {}, []
            for key, (_, content) in zip(keys, entries):
                value = self.cache.get(key)
                if value and self.clock() - value[0] < self.ttl:
                    found[key] = value[1]
                    self.cache.move_to_end(key)
                else:
                    missing.append((key, content))
            blocked = self.clock() < self.blocked_until
        if missing:
            if blocked:
                raise RuntimeError("embedding circuit open")
            from ..core.llm import get_embedding
            try:
                # Never hold the cache lock across a remote call (other tenants can hit cache).
                vectors = (embedder or get_embedding()).embed_documents([content for _, content in missing])
                if len(vectors) != len(missing):
                    raise ValueError("incomplete embedding batch")
                normalized = [unit_vector(v) for v in vectors]
                if len({len(v) for v in normalized}) != 1:
                    raise ValueError("inconsistent dimensions")
                with self.lock:
                    for (key, _), vector in zip(missing, normalized):
                        found[key] = vector
                        self.cache[key] = (self.clock(), vector)
                    while len(self.cache) > self.capacity:
                        self.cache.popitem(last=False)
            except Exception:
                self.unavailable()
                raise
        return [found[key] for key in keys]

    def rank(self, user_id, query, items, *, threshold=None, embedder=None, model=None):
        items = [item for item in items if item.user_id == user_id and is_effective(item)]
        if not items:
            return [], "empty"
        threshold = get_settings().memory_semantic_threshold if threshold is None else threshold
        try:
            vectors = self.vectors(user_id, [("query", query)] + [(item.id, item.content) for item in items],
                                   embedder=embedder, model=model)
            if any(len(v) != len(vectors[0]) for v in vectors):
                raise ValueError("model dimensions changed")
            scores = [sum(a*b for a,b in zip(vectors[0], v)) for v in vectors[1:]]
            ranked = [(item, score) for item, score in zip(items, scores) if score >= threshold]
            return sorted(ranked, key=lambda pair: pair[1], reverse=True), "semantic"
        except Exception:
            ranked = [(item, lexical_score(item.content, query)) for item in items]
            return sorted([pair for pair in ranked if pair[1] > 0], key=lambda pair: pair[1], reverse=True), "lexical"


@lru_cache(maxsize=1)
def get_semantic_cache():
    return SemanticMemoryCache()
