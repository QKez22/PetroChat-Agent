"""Long-term memory management API.

Phase 6.1 exposes explicit CRUD-style endpoints for the memory store. Agent
auto-write and retrieval are implemented later, after the data model is stable.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core.models import AuthUser
from ..memory import MemoryEvent, MemoryItem, get_long_term_memory_store
from .auth import CurrentUserDep

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    memory_type: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=1000)
    source: str = Field(default="manual", max_length=64)
    confidence: float = Field(default=1.0, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    actor_id: str | None = Field(default=None, max_length=64)
    expires_at: str | None = Field(default=None, max_length=64)


class MemoryUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=1000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    metadata: dict[str, Any] | None = None
    actor_id: str | None = Field(default=None, max_length=64)
    reason: str = Field(default="update memory", max_length=200)


class MemoryActionRequest(BaseModel):
    actor_id: str | None = Field(default=None, max_length=64)
    reason: str = Field(default="", max_length=200)


class MemoryBatchActionRequest(BaseModel):
    memory_ids: list[str] = Field(min_length=1, max_length=50)
    actor_id: str | None = Field(default=None, max_length=64)
    reason: str = Field(default="batch disable memory", max_length=200)


class MemoryResponse(BaseModel):
    id: str
    user_id: str
    memory_type: str
    content: str
    source: str
    confidence: float
    status: Literal["active", "disabled", "deleted"]
    metadata: dict[str, Any]
    created_at: str
    updated_at: str
    expires_at: str | None = None


class MemoryEventResponse(BaseModel):
    id: str
    memory_id: str
    user_id: str
    event_type: Literal["created", "updated", "disabled", "deleted", "accessed"]
    actor_id: str | None = None
    reason: str
    payload: dict[str, Any]
    created_at: str


class MemoryConflictResponse(BaseModel):
    memory: MemoryResponse
    score: float
    reason: str


class MemoryBatchActionResponse(BaseModel):
    requested: int
    updated: int
    missing: list[str]
    items: list[MemoryResponse]


def _to_memory_response(item: MemoryItem) -> MemoryResponse:
    return MemoryResponse(
        id=item.id,
        user_id=item.user_id,
        memory_type=item.memory_type,
        content=item.content,
        source=item.source,
        confidence=item.confidence,
        status=item.status,
        metadata=item.metadata,
        created_at=item.created_at,
        updated_at=item.updated_at,
        expires_at=item.expires_at,
    )


def _to_event_response(event: MemoryEvent) -> MemoryEventResponse:
    return MemoryEventResponse(
        id=event.id,
        memory_id=event.memory_id,
        user_id=event.user_id,
        event_type=event.event_type,
        actor_id=event.actor_id,
        reason=event.reason,
        payload=event.payload,
        created_at=event.created_at,
    )


def _tokens(value: str) -> set[str]:
    normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
    return {part for part in normalized.split() if len(part) >= 2}


def _conflict_score(current: MemoryItem, candidate: MemoryItem) -> tuple[float, str]:
    if current.id == candidate.id:
        return 0, ""
    if current.user_id != candidate.user_id or current.memory_type != candidate.memory_type:
        return 0, ""

    current_text = current.content.strip().lower()
    candidate_text = candidate.content.strip().lower()
    if current_text and (current_text in candidate_text or candidate_text in current_text):
        return 0.95, "同用户同类型记忆内容存在包含关系"

    current_tokens = _tokens(current.content)
    candidate_tokens = _tokens(candidate.content)
    if not current_tokens or not candidate_tokens:
        return 0, ""
    overlap = len(current_tokens & candidate_tokens)
    score = overlap / max(len(current_tokens), len(candidate_tokens))
    if score >= 0.45:
        return round(score, 3), "同用户同类型记忆关键词重叠较高"
    return 0, ""


def _resolve_user_id(requested_user_id: str | None, user: AuthUser) -> str:
    requested = (requested_user_id or "").strip()
    if user.role == "admin" and requested:
        return requested
    if requested and requested != user.user_id:
        raise HTTPException(status_code=403, detail="cannot access another user's memories")
    return user.user_id


def _ensure_memory_access(item: MemoryItem, user: AuthUser) -> None:
    if user.role != "admin" and item.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="cannot access another user's memories")


def _actor_id(req_actor_id: str | None, user: AuthUser) -> str:
    if user.role == "admin" and req_actor_id:
        return req_actor_id
    return user.user_id


@router.get("", response_model=list[MemoryResponse], summary="长期记忆列表")
async def list_memories(
    user: CurrentUserDep,
    user_id: str,
    status: Literal["active", "disabled", "deleted", "all"] = "active",
    memory_type: str | None = None,
    q: str | None = None,
    limit: int = 50,
) -> list[MemoryResponse]:
    store = get_long_term_memory_store()
    target_user_id = _resolve_user_id(user_id, user)
    try:
        items = store.list_memories(
            user_id=target_user_id,
            status=status,
            memory_type=memory_type,
            q=q,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [_to_memory_response(item) for item in items]


@router.post("", response_model=MemoryResponse, summary="创建长期记忆")
async def create_memory(req: MemoryCreateRequest, user: CurrentUserDep) -> MemoryResponse:
    store = get_long_term_memory_store()
    target_user_id = _resolve_user_id(req.user_id, user)
    try:
        item = store.create_memory(
            user_id=target_user_id,
            memory_type=req.memory_type,
            content=req.content,
            source=req.source,
            confidence=req.confidence,
            metadata=req.metadata,
            actor_id=_actor_id(req.actor_id, user),
            expires_at=req.expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_memory_response(item)


@router.patch("/{memory_id}", response_model=MemoryResponse, summary="更新长期记忆")
async def update_memory(memory_id: str, req: MemoryUpdateRequest, user: CurrentUserDep) -> MemoryResponse:
    store = get_long_term_memory_store()
    try:
        current = store.get_memory(memory_id)
        if current is None:
            raise HTTPException(status_code=404, detail="memory not found")
        _ensure_memory_access(current, user)
        item = store.update_memory(
            memory_id,
            content=req.content,
            metadata=req.metadata,
            confidence=req.confidence,
            actor_id=_actor_id(req.actor_id, user),
            reason=req.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return _to_memory_response(item)


@router.post("/batch/disable", response_model=MemoryBatchActionResponse, summary="批量禁用长期记忆")
async def batch_disable_memories(req: MemoryBatchActionRequest, user: CurrentUserDep) -> MemoryBatchActionResponse:
    store = get_long_term_memory_store()
    updated: list[MemoryItem] = []
    missing: list[str] = []
    seen: set[str] = set()
    for memory_id in req.memory_ids:
        if memory_id in seen:
            continue
        seen.add(memory_id)
        try:
            current = store.get_memory(memory_id)
            if current is None:
                missing.append(memory_id)
                continue
            _ensure_memory_access(current, user)
            item = store.disable_memory(
                memory_id,
                actor_id=_actor_id(req.actor_id, user),
                reason=req.reason or "batch disable memory",
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if item is None:
            missing.append(memory_id)
        else:
            updated.append(item)
    return MemoryBatchActionResponse(
        requested=len(req.memory_ids),
        updated=len(updated),
        missing=missing,
        items=[_to_memory_response(item) for item in updated],
    )


@router.get("/{memory_id}/conflicts", response_model=list[MemoryConflictResponse], summary="长期记忆冲突提示")
async def memory_conflicts(memory_id: str, user: CurrentUserDep, limit: int = 5) -> list[MemoryConflictResponse]:
    store = get_long_term_memory_store()
    try:
        current = store.get_memory(memory_id)
        if current is None:
            raise HTTPException(status_code=404, detail="memory not found")
        _ensure_memory_access(current, user)
        candidates = store.list_memories(
            user_id=current.user_id,
            status="active",
            memory_type=current.memory_type,
            limit=100,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    scored: list[tuple[float, str, MemoryItem]] = []
    for candidate in candidates:
        score, reason = _conflict_score(current, candidate)
        if score > 0:
            scored.append((score, reason, candidate))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        MemoryConflictResponse(
            memory=_to_memory_response(item),
            score=score,
            reason=reason,
        )
        for score, reason, item in scored[: max(1, min(limit, 20))]
    ]


@router.post("/{memory_id}/disable", response_model=MemoryResponse, summary="禁用长期记忆")
async def disable_memory(memory_id: str, req: MemoryActionRequest, user: CurrentUserDep) -> MemoryResponse:
    store = get_long_term_memory_store()
    try:
        current = store.get_memory(memory_id)
        if current is None:
            raise HTTPException(status_code=404, detail="memory not found")
        _ensure_memory_access(current, user)
        item = store.disable_memory(
            memory_id,
            actor_id=_actor_id(req.actor_id, user),
            reason=req.reason or "disable memory",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return _to_memory_response(item)


@router.delete("/{memory_id}", response_model=MemoryResponse, summary="软删除长期记忆")
async def delete_memory(
    memory_id: str,
    user: CurrentUserDep,
    actor_id: str | None = None,
    reason: str = "delete memory",
) -> MemoryResponse:
    store = get_long_term_memory_store()
    try:
        current = store.get_memory(memory_id)
        if current is None:
            raise HTTPException(status_code=404, detail="memory not found")
        _ensure_memory_access(current, user)
        item = store.delete_memory(memory_id, actor_id=_actor_id(actor_id, user), reason=reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return _to_memory_response(item)


@router.get("/{memory_id}/events", response_model=list[MemoryEventResponse], summary="长期记忆审计事件")
async def list_memory_events(memory_id: str, user: CurrentUserDep, limit: int = 50) -> list[MemoryEventResponse]:
    store = get_long_term_memory_store()
    try:
        current = store.get_memory(memory_id)
        if current is None:
            raise HTTPException(status_code=404, detail="memory not found")
        _ensure_memory_access(current, user)
        events = store.list_events(memory_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [_to_event_response(event) for event in events]
