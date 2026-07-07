"""Optional Mem0 integration with candidate and active collections.

Mem0 candidate collection runs `infer=True` to extract possible memories from a
conversation. MySQL remains the governed source of truth. Only accepted MySQL
active memories are synced into the active Mem0 collection for semantic recall.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from loguru import logger

from ..core import get_settings
from .long_term import MemoryItem


@dataclass(frozen=True)
class Mem0Candidate:
    id: str
    content: str
    score: float
    metadata: dict[str, Any]


@dataclass(frozen=True)
class Mem0SearchResult:
    id: str
    memory_id: str
    content: str
    score: float
    metadata: dict[str, Any]


class Mem0MemoryAdapter:
    def __init__(
        self,
        memory_client: Any | None = None,
        *,
        candidate_client: Any | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._active_client = memory_client
        self._candidate_client = candidate_client
        self._enabled_override = enabled

    @property
    def enabled(self) -> bool:
        if self._enabled_override is not None:
            return self._enabled_override
        return get_settings().mem0_enabled

    def extract_candidates(
        self,
        *,
        messages: list[dict[str, str]],
        user_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[Mem0Candidate]:
        """Run Mem0 auto extraction in the isolated candidate collection."""

        if not self.enabled or not messages:
            return []
        candidate_metadata = {
            "stage": "candidate",
            "user_id": user_id,
            **(metadata or {}),
        }
        try:
            response = self.candidate_client.add(
                messages,
                user_id=user_id,
                metadata=candidate_metadata,
                infer=True,
            )
        except Exception as exc:
            logger.warning("Mem0 candidate extraction failed: {}", exc)
            return []
        return self._parse_candidates(response)

    def sync_created(self, item: MemoryItem) -> None:
        if not self.enabled or item.status != "active":
            return
        try:
            self.active_client.add(
                item.content,
                user_id=item.user_id,
                metadata=self._metadata(item),
                infer=False,
            )
        except Exception as exc:
            logger.warning("Mem0 active sync create failed: {}", exc)

    def sync_updated(self, item: MemoryItem) -> None:
        if not self.enabled:
            return
        if item.status != "active":
            self.sync_removed(item)
            return
        try:
            memory_ids = self._find_mem0_ids(item.user_id, item.id)
            if not memory_ids:
                self.sync_created(item)
                return
            for mem0_id in memory_ids:
                self.active_client.update(mem0_id, data=item.content, metadata=self._metadata(item))
        except Exception as exc:
            logger.warning("Mem0 active sync update failed: {}", exc)

    def sync_removed(self, item: MemoryItem) -> None:
        if not self.enabled:
            return
        try:
            memory_ids = self._find_mem0_ids(item.user_id, item.id)
            for mem0_id in memory_ids:
                self.active_client.delete(mem0_id)
        except Exception as exc:
            logger.warning("Mem0 active sync delete failed: {}", exc)

    def reset_index(self) -> None:
        if not self.enabled:
            return
        self.active_client.reset()

    def reset_candidate_index(self) -> None:
        if not self.enabled:
            return
        self.candidate_client.reset()

    def search(self, *, user_id: str, query: str, limit: int = 5) -> list[Mem0SearchResult]:
        if not self.enabled or not query.strip():
            return []
        try:
            response = self.active_client.search(
                query=query,
                top_k=max(1, limit),
                filters={"user_id": user_id, "status": "active"},
                threshold=get_settings().mem0_search_threshold,
            )
        except Exception as exc:
            logger.warning("Mem0 active recall failed: {}", exc)
            return []
        return self._parse_results(response)

    @property
    def active_client(self) -> Any:
        if self._active_client is None:
            self._active_client = _build_mem0_client(get_settings().mem0_chroma_collection)
        return self._active_client

    @property
    def candidate_client(self) -> Any:
        if self._candidate_client is None:
            self._candidate_client = _build_mem0_client(get_settings().mem0_candidate_chroma_collection)
        return self._candidate_client

    def _find_mem0_ids(self, user_id: str, memory_id: str) -> list[str]:
        response = self.active_client.get_all(
            filters={
                "user_id": user_id,
                "petrochat_memory_id": memory_id,
            },
            top_k=20,
        )
        return [
            str(row["id"])
            for row in self._raw_results(response)
            if row.get("id") and _metadata(row).get("petrochat_memory_id") == memory_id
        ]

    def _metadata(self, item: MemoryItem) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "stage": "active",
            "petrochat_memory_id": item.id,
            "memory_type": item.memory_type,
            "source": item.source,
            "confidence": item.confidence,
            "status": item.status,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for key, value in item.metadata.items():
            if isinstance(value, str | int | float | bool):
                metadata[f"petrochat_{key}"] = value
        return metadata

    def _parse_candidates(self, response: Any) -> list[Mem0Candidate]:
        parsed: list[Mem0Candidate] = []
        for row in self._raw_results(response):
            content = str(row.get("memory") or row.get("text") or row.get("content") or "").strip()
            if not content:
                continue
            parsed.append(
                Mem0Candidate(
                    id=str(row.get("id") or ""),
                    content=content,
                    score=float(row.get("score") or row.get("confidence") or 0.75),
                    metadata=_metadata(row),
                )
            )
        return parsed

    def _parse_results(self, response: Any) -> list[Mem0SearchResult]:
        parsed: list[Mem0SearchResult] = []
        for row in self._raw_results(response):
            content = str(row.get("memory") or row.get("text") or row.get("content") or "").strip()
            if not content:
                continue
            metadata = _metadata(row)
            if metadata.get("stage") not in {None, "active"}:
                continue
            if metadata.get("status") not in {None, "active"}:
                continue
            parsed.append(
                Mem0SearchResult(
                    id=str(row.get("id") or metadata.get("petrochat_memory_id") or ""),
                    memory_id=str(metadata.get("petrochat_memory_id") or row.get("id") or ""),
                    content=content,
                    score=float(row.get("score") or row.get("relevance") or 0.0),
                    metadata=metadata,
                )
            )
        return parsed

    def _raw_results(self, response: Any) -> list[dict[str, Any]]:
        if isinstance(response, dict):
            rows = response.get("results") or response.get("memories") or []
        else:
            rows = response or []
        return [row for row in rows if isinstance(row, dict)]


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") or row.get("payload") or {}
    return metadata if isinstance(metadata, dict) else {}


def _build_mem0_client(collection_name: str) -> Any:
    try:
        from mem0 import Memory
    except ImportError as exc:
        raise RuntimeError("mem0ai is not installed") from exc

    settings = get_settings()
    settings.mem0_history_db_path.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": collection_name,
                "host": settings.chroma_host,
                "port": settings.chroma_port,
            },
        },
        "llm": {
            "provider": settings.mem0_llm_provider,
            "config": {
                "model": settings.deepseek_chat_model,
                "api_key": settings.deepseek_api_key.get_secret_value(),
                "deepseek_base_url": settings.deepseek_base_url,
                "temperature": 0.1,
                "max_tokens": 1200,
            },
        },
        "embedder": {
            "provider": settings.mem0_embedder_provider,
            "config": {
                "model": settings.embedding_model,
                "api_key": settings.dashscope_api_key.get_secret_value(),
                "openai_base_url": settings.dashscope_base_url,
                "embedding_dims": settings.embedding_dim,
            },
        },
        "history_db_path": str(settings.mem0_history_db_path),
        "custom_instructions": (
            "Only remember durable user preferences, default filters, project preferences, "
            "historical decisions, corrections, and stable business context. Do not remember "
            "domain-document facts, SQL query results, secrets, or one-off questions."
        ),
    }
    return Memory.from_config(config)


@lru_cache(maxsize=1)
def get_mem0_memory_adapter() -> Mem0MemoryAdapter:
    return Mem0MemoryAdapter()
