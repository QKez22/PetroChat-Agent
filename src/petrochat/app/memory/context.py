"""Long-term memory recall and conservative write-back helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import SystemMessage
from loguru import logger

from .long_term import LongTermMemoryStore, MemoryItem, get_long_term_memory_store

_MEMORY_INTENT_PAT = re.compile(
    r"(记住|以后|今后|下次|默认|常用|偏好|我负责|我主要看|固定条件|默认条件)"
)
_TOKEN_PAT = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_]{2,}")


@dataclass(frozen=True)
class RecalledMemory:
    id: str
    memory_type: str
    content: str
    source: str
    confidence: float
    metadata: dict[str, Any]

    @classmethod
    def from_item(cls, item: MemoryItem) -> RecalledMemory:
        return cls(
            id=item.id,
            memory_type=item.memory_type,
            content=item.content,
            source=item.source,
            confidence=item.confidence,
            metadata=item.metadata,
        )

    def to_state(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "memory_type": self.memory_type,
            "content": self.content,
            "source": self.source,
            "confidence": self.confidence,
            "metadata": self.metadata,
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
) -> tuple[list[RecalledMemory], str]:
    """Recall active user memories and return structured data plus prompt text."""

    if not _is_numeric_user(user_id):
        return [], ""

    store = store or get_long_term_memory_store()
    try:
        items = store.list_memories(user_id=user_id, status="active", limit=max(limit * 4, limit))
    except Exception as exc:
        logger.warning("长期记忆召回失败: {}", exc)
        return [], ""

    selected = _rank_memories(items, question)[: max(0, limit)]
    memories = [RecalledMemory.from_item(item) for item in selected]
    return memories, format_long_term_context(memories)


def format_long_term_context(memories: list[RecalledMemory]) -> str:
    if not memories:
        return ""
    lines = []
    for idx, mem in enumerate(memories, start=1):
        lines.append(
            f"{idx}. [memory:{mem.id}] type={mem.memory_type}; "
            f"confidence={mem.confidence:.2f}; content={mem.content}"
        )
    return "\n".join(lines)


def build_memory_system_message(context: str) -> SystemMessage | None:
    if not context.strip():
        return None
    return SystemMessage(
        content=(
            "【用户长期记忆】\n"
            "以下内容来自该用户显式管理或受控写入的长期记忆。"
            "它只能用于理解用户偏好、常用筛选条件和业务上下文；"
            "不能替代规范文档、数据库事实或 SQL 安全规则。\n"
            f"{context}"
        )
    )


def augment_question_with_memory(question: str, context: str) -> str:
    if not context.strip():
        return question
    return (
        f"{question}\n\n"
        "【用户长期记忆】\n"
        f"{context}\n\n"
        "请仅在问题语义需要默认条件或用户上下文时使用长期记忆；"
        "长期记忆不能覆盖用户本轮明确条件。"
    )


def extract_memory_candidates(question: str, route: str | None = None) -> list[dict[str, Any]]:
    """Extract only explicit, user-controlled memory candidates."""

    normalized = _compact(question)
    if not normalized or not _MEMORY_INTENT_PAT.search(normalized):
        return []

    memory_type = "preference"
    if any(word in normalized for word in ("默认", "条件", "筛选", "统计", "查询", "清单")):
        memory_type = "query_filter"
    if any(word in normalized for word in ("我负责", "部门", "专业", "区域", "装置", "设备")):
        memory_type = "business_context"

    return [{
        "memory_type": memory_type,
        "content": f"用户显式偏好/上下文：{normalized}",
        "confidence": 0.72,
        "metadata": {
            "extractor": "rule_v1",
            "route": route or "unknown",
            "trigger": "explicit_memory_intent",
        },
    }]


def write_memory_candidates(
    *,
    user_id: str,
    question: str,
    route: str | None = None,
    store: LongTermMemoryStore | None = None,
) -> list[MemoryWriteResult]:
    """Write conservative memory candidates and return newly created ids."""

    if not _is_numeric_user(user_id):
        return []

    candidates = extract_memory_candidates(question, route=route)
    if not candidates:
        return []

    store = store or get_long_term_memory_store()
    try:
        existing = store.list_memories(user_id=user_id, status="active", limit=200)
    except Exception as exc:
        logger.warning("长期记忆写入前读取失败: {}", exc)
        return []

    existing_contents = {_compact(item.content) for item in existing}
    written: list[MemoryWriteResult] = []
    for candidate in candidates:
        content = candidate["content"]
        if _compact(content) in existing_contents:
            continue
        try:
            item = store.create_memory(
                user_id=user_id,
                memory_type=candidate["memory_type"],
                content=content,
                source="agent_rule_extracted",
                confidence=candidate["confidence"],
                metadata=candidate["metadata"],
                actor_id=user_id,
            )
        except Exception as exc:
            logger.warning("长期记忆写入失败: {}", exc)
            continue
        existing_contents.add(_compact(content))
        written.append(MemoryWriteResult(id=item.id, memory_type=item.memory_type, content=item.content))
    return written


def _rank_memories(items: list[MemoryItem], question: str) -> list[MemoryItem]:
    q_tokens = set(_TOKEN_PAT.findall(question))

    def score(item: MemoryItem) -> tuple[int, float, str]:
        content_tokens = set(_TOKEN_PAT.findall(item.content))
        overlap = len(q_tokens & content_tokens)
        type_bonus = 1 if item.memory_type in {"preference", "query_filter", "business_context"} else 0
        return overlap + type_bonus, item.confidence, item.updated_at

    return sorted(items, key=score, reverse=True)


def _is_numeric_user(user_id: str) -> bool:
    try:
        return int(user_id) >= 0
    except (TypeError, ValueError):
        return False


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())
