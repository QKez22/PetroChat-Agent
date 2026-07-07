"""Long-term memory extraction, recall, and prompt injection helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import SystemMessage
from loguru import logger

from .long_term import LongTermMemoryStore, MemoryItem, get_long_term_memory_store
from .mem0_adapter import Mem0SearchResult, get_mem0_memory_adapter
from .policy import accept_mem0_candidate, build_recall_policy, should_extract_memory

_TOKEN_PAT = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_]{2,}")


@dataclass(frozen=True)
class RecalledMemory:
    id: str
    memory_id: str
    memory_type: str
    content: str
    source: str
    confidence: float
    metadata: dict[str, Any]
    recall_source: str = "mysql"
    score: float | None = None
    updated_at: str = ""

    @classmethod
    def from_item(
        cls,
        item: MemoryItem,
        *,
        recall_source: str = "mysql",
        score: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RecalledMemory:
        merged_metadata = dict(item.metadata)
        if metadata:
            merged_metadata.update(metadata)
        return cls(
            id=item.id,
            memory_id=item.id,
            memory_type=item.memory_type,
            content=item.content,
            source=item.source,
            confidence=item.confidence,
            metadata=merged_metadata,
            recall_source=recall_source,
            score=score,
            updated_at=item.updated_at,
        )

    def to_state(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "memory_id": self.memory_id,
            "memory_type": self.memory_type,
            "content": self.content,
            "source": self.source,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "recall_source": self.recall_source,
            "score": self.score,
        }


@dataclass(frozen=True)
class MemoryWriteResult:
    id: str
    memory_type: str
    content: str


def recall_long_term_memories(
    *,
    user_id: str,
    question: str,
    limit: int = 5,
    store: LongTermMemoryStore | None = None,
    route_hint: str | None = None,
) -> tuple[list[RecalledMemory], str]:
    """Recall active memories. Mem0 provides ids; MySQL validates the records."""

    if not _is_numeric_user(user_id):
        return [], ""

    store = store or get_long_term_memory_store()
    policy = build_recall_policy(question, route_hint=route_hint)
    memories: list[RecalledMemory] = []

    if policy.use_mem0:
        memories = _recall_from_mem0(
            user_id=user_id,
            question=question,
            limit=limit,
            memory_types=policy.memory_types,
            store=store,
        )

    if len(memories) < limit:
        memories = _merge_mysql_fallback(
            user_id=user_id,
            question=question,
            memories=memories,
            limit=limit,
            memory_types=policy.memory_types,
            store=store,
        )
    return memories[:limit], format_long_term_context(memories[:limit])


def format_long_term_context(memories: list[RecalledMemory]) -> str:
    if not memories:
        return ""
    lines = []
    for idx, mem in enumerate(memories, start=1):
        lines.append(
            f"{idx}. [memory:{mem.id}] type={mem.memory_type}; "
            f"source={mem.recall_source}; score={mem.score}; "
            f"confidence={mem.confidence:.2f}; content={mem.content}"
        )
    return "\n".join(lines)


def build_memory_system_message(context: str) -> SystemMessage | None:
    if not context.strip():
        return None
    return SystemMessage(
        content=(
            "用户长期记忆\n"
            "[User long-term memory]\n"
            "The following memories are governed user context. Use them only for preferences, "
            "default filters, project context, historical decisions, or corrections. They do not "
            "replace RAG documents, database facts, or SQL safety rules.\n"
            f"{context}"
        )
    )


def augment_question_with_memory(question: str, context: str) -> str:
    if not context.strip():
        return question
    return (
        f"{question}\n\n"
        "[User long-term memory]\n"
        f"{context}\n\n"
        "Use this memory only when the question needs user defaults or context. "
        "Never override explicit constraints in the current question."
    )


def extract_memory_candidates(question: str, route: str | None = None) -> list[dict[str, Any]]:
    """Compatibility wrapper: candidate extraction is now delegated to Mem0."""

    if not should_extract_memory(question, route=route):
        return []
    return [{
        "memory_type": "preference",
        "content": _compact(question),
        "confidence": 0.5,
        "metadata": {"extractor": "trigger_only", "route": route or "unknown"},
    }]


def write_memory_candidates(
    *,
    user_id: str,
    question: str,
    answer: str = "",
    route: str | None = None,
    store: LongTermMemoryStore | None = None,
) -> list[MemoryWriteResult]:
    """Extract with Mem0 candidate collection, filter, persist to MySQL, then sync active index."""

    if not _is_numeric_user(user_id) or not should_extract_memory(question, answer=answer, route=route):
        return []

    store = store or get_long_term_memory_store()
    try:
        existing = store.list_memories(user_id=user_id, status="active", limit=200)
    except Exception as exc:
        logger.warning("long-term memory pre-read failed: {}", exc)
        return []

    adapter = get_mem0_memory_adapter()
    candidates = adapter.extract_candidates(
        messages=_memory_messages(question, answer),
        user_id=user_id,
        metadata={"route": route or "unknown"},
    )
    if not candidates:
        return []

    existing_contents = {_compact(item.content) for item in existing}
    written: list[MemoryWriteResult] = []
    for candidate in candidates:
        accepted = accept_mem0_candidate(
            content=candidate.content,
            confidence=candidate.score,
            existing_contents=existing_contents,
            route=route,
            metadata={
                "candidate_id": candidate.id,
                "candidate_stage": "candidate",
                **candidate.metadata,
            },
        )
        if accepted is None:
            continue
        try:
            item = store.create_memory(
                user_id=user_id,
                memory_type=accepted.memory_type,
                content=accepted.content,
                source="mem0_infer",
                confidence=accepted.confidence,
                metadata=accepted.metadata,
                actor_id=user_id,
            )
        except Exception as exc:
            logger.warning("long-term memory write failed: {}", exc)
            continue
        existing_contents.add(_compact(item.content))
        written.append(MemoryWriteResult(id=item.id, memory_type=item.memory_type, content=item.content))
    return written


def _recall_from_mem0(
    *,
    user_id: str,
    question: str,
    limit: int,
    memory_types: set[str],
    store: LongTermMemoryStore,
) -> list[RecalledMemory]:
    results = get_mem0_memory_adapter().search(user_id=user_id, query=question, limit=max(limit * 2, limit))
    memories: list[RecalledMemory] = []
    seen: set[str] = set()
    for result in results:
        if result.memory_id in seen:
            continue
        item = _validated_mysql_memory(result, user_id=user_id, memory_types=memory_types, store=store)
        if item is None:
            continue
        memories.append(
            RecalledMemory.from_item(
                item,
                recall_source="mem0",
                score=result.score,
                metadata={"mem0_id": result.id},
            )
        )
        seen.add(item.id)
        if len(memories) >= limit:
            break
    return memories


def _validated_mysql_memory(
    result: Mem0SearchResult,
    *,
    user_id: str,
    memory_types: set[str],
    store: LongTermMemoryStore,
) -> MemoryItem | None:
    if not result.memory_id:
        return None
    try:
        item = store.get_memory(result.memory_id)
    except Exception as exc:
        logger.warning("memory id validation failed: {}", exc)
        return None
    if item is None or item.status != "active":
        return None
    if item.user_id != user_id or item.memory_type not in memory_types:
        return None
    return item


def _merge_mysql_fallback(
    *,
    user_id: str,
    question: str,
    memories: list[RecalledMemory],
    limit: int,
    memory_types: set[str],
    store: LongTermMemoryStore,
) -> list[RecalledMemory]:
    existing_ids = {memory.memory_id for memory in memories}
    try:
        items: list[MemoryItem] = []
        per_type_limit = max(limit * 4, limit)
        for memory_type in sorted(memory_types):
            items.extend(
                store.list_memories(
                    user_id=user_id,
                    status="active",
                    memory_type=memory_type,
                    limit=per_type_limit,
                )
            )
    except Exception as exc:
        logger.warning("MySQL memory fallback failed: {}", exc)
        return memories

    for item in _rank_memories(items, question):
        if item.id in existing_ids:
            continue
        memories.append(RecalledMemory.from_item(item, recall_source="mysql", score=_memory_score(item, question)))
        existing_ids.add(item.id)
        if len(memories) >= limit:
            break
    return sorted(
        memories,
        key=lambda mem: (mem.score or 0.0, mem.updated_at, 1 if mem.recall_source == "mem0" else 0),
        reverse=True,
    )


def _rank_memories(items: list[MemoryItem], question: str) -> list[MemoryItem]:
    return sorted(items, key=lambda item: (_memory_score(item, question), item.updated_at), reverse=True)


def _memory_score(item: MemoryItem, question: str) -> float:
    q_tokens = set(_TOKEN_PAT.findall(question))
    content_tokens = set(_TOKEN_PAT.findall(item.content))
    overlap = len(q_tokens & content_tokens)
    type_bonus = 1 if item.memory_type in {"preference", "query_filter", "business_context"} else 0
    lexical = min((overlap + type_bonus) / 5, 1.0)
    return round(lexical * 0.7 + item.confidence * 0.3, 4)


def _memory_messages(question: str, answer: str) -> list[dict[str, str]]:
    messages = [{"role": "user", "content": question}]
    if answer.strip():
        messages.append({"role": "assistant", "content": answer})
    return messages


def _is_numeric_user(user_id: str) -> bool:
    try:
        return int(user_id) >= 0
    except (TypeError, ValueError):
        return False


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())
