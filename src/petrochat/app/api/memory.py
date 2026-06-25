"""Long-term memory management API.

Phase 6.1 exposes explicit CRUD-style endpoints for the memory store. Agent
auto-write and retrieval are implemented later, after the data model is stable.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..memory import MemoryEvent, MemoryItem, get_long_term_memory_store

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


@router.get("", response_model=list[MemoryResponse], summary="长期记忆列表")
async def list_memories(
    user_id: str,
    status: Literal["active", "disabled", "deleted", "all"] = "active",
    memory_type: str | None = None,
    limit: int = 50,
) -> list[MemoryResponse]:
    store = get_long_term_memory_store()
    try:
        items = store.list_memories(
            user_id=user_id,
            status=status,
            memory_type=memory_type,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [_to_memory_response(item) for item in items]


@router.post("", response_model=MemoryResponse, summary="创建长期记忆")
async def create_memory(req: MemoryCreateRequest) -> MemoryResponse:
    store = get_long_term_memory_store()
    try:
        item = store.create_memory(
            user_id=req.user_id,
            memory_type=req.memory_type,
            content=req.content,
            source=req.source,
            confidence=req.confidence,
            metadata=req.metadata,
            actor_id=req.actor_id,
            expires_at=req.expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_memory_response(item)


@router.patch("/{memory_id}", response_model=MemoryResponse, summary="更新长期记忆")
async def update_memory(memory_id: str, req: MemoryUpdateRequest) -> MemoryResponse:
    store = get_long_term_memory_store()
    try:
        item = store.update_memory(
            memory_id,
            content=req.content,
            metadata=req.metadata,
            confidence=req.confidence,
            actor_id=req.actor_id,
            reason=req.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return _to_memory_response(item)


@router.post("/{memory_id}/disable", response_model=MemoryResponse, summary="禁用长期记忆")
async def disable_memory(memory_id: str, req: MemoryActionRequest) -> MemoryResponse:
    store = get_long_term_memory_store()
    try:
        item = store.disable_memory(
            memory_id,
            actor_id=req.actor_id,
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
    actor_id: str | None = None,
    reason: str = "delete memory",
) -> MemoryResponse:
    store = get_long_term_memory_store()
    try:
        item = store.delete_memory(memory_id, actor_id=actor_id, reason=reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return _to_memory_response(item)


@router.get("/{memory_id}/events", response_model=list[MemoryEventResponse], summary="长期记忆审计事件")
async def list_memory_events(memory_id: str, limit: int = 50) -> list[MemoryEventResponse]:
    store = get_long_term_memory_store()
    try:
        if store.get_memory(memory_id) is None:
            raise HTTPException(status_code=404, detail="memory not found")
        events = store.list_events(memory_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [_to_event_response(event) for event in events]
