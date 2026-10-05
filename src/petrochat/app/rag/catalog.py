"""MySQL 权威清单、版本与访问策略；请求内固定同一个不可变快照。"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from typing import Literal

from langchain_core.documents import Document
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import JSON, Column, MetaData, String, Table, insert, select, update

from ..core.config import get_settings
from ..sql.engine import get_app_engine

schema = MetaData()
manifests = Table(
    "agent_rag_manifest",
    schema,
    Column("snapshot_id", String(64), primary_key=True),
    Column("collection_name", String(128), nullable=False),
    Column("payload", JSON, nullable=False),
)
active = Table(
    "agent_rag_active",
    schema,
    Column("name", String(32), primary_key=True),
    Column("snapshot_id", String(64), nullable=False),
)


class VersionPolicy(BaseModel):
    source_doc: str
    document_id: str
    version_id: str
    effective_from: date | None = None
    effective_to: date | None = None
    status: Literal["verified", "unknown"] = "unknown"
    allowed_users: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def interval(self):
        if self.status == "verified" and self.effective_from is None:
            raise ValueError("已核实版本必须有生效日期")
        if self.effective_to and (
            not self.effective_from or self.effective_to <= self.effective_from
        ):
            raise ValueError("有效期必须为非空 [from, to)")
        return self


class PolicyError(ValueError):
    pass


def select_versions(
    versions: list[VersionPolicy], user_id: str, as_of: date | None
) -> list[VersionPolicy]:
    allowed = [
        v for v in versions if user_id and ("*" in v.allowed_users or user_id in v.allowed_users)
    ]
    when = as_of or date.today()
    chosen = [
        v
        for v in allowed
        if (v.status == "unknown" and as_of is None)
        or (
            v.status == "verified"
            and v.effective_from <= when
            and (v.effective_to is None or when < v.effective_to)
        )
    ]
    groups: dict[str, list] = {}
    for v in chosen:
        groups.setdefault(v.document_id, []).append(v)
    if any(len(v) > 1 for v in groups.values()):
        raise PolicyError("存在重叠或未核实版本，需人工核对适用版本。")
    return chosen


class Catalog:
    def __init__(self, engine=None):
        self.engine = engine or get_app_engine()

    def initialize(self):
        schema.create_all(self.engine)

    def publish(self, snapshot_id: str, collection_name: str, payload: dict):
        with self.engine.begin() as conn:
            existing = (
                conn.execute(select(manifests).where(manifests.c.snapshot_id == snapshot_id))
                .mappings()
                .first()
            )
            if existing:
                if existing["payload"] != payload or existing["collection_name"] != collection_name:
                    raise ValueError("不可覆盖已有索引清单")
            else:
                conn.execute(
                    insert(manifests).values(
                        snapshot_id=snapshot_id, collection_name=collection_name, payload=payload
                    )
                )
            row = conn.execute(
                select(active).where(active.c.name == "specs").with_for_update()
            ).first()
            if row:
                conn.execute(
                    update(active).where(active.c.name == "specs").values(snapshot_id=snapshot_id)
                )
            else:
                conn.execute(insert(active).values(name="specs", snapshot_id=snapshot_id))

    def current(self) -> dict:
        with self.engine.connect() as conn:
            row = (
                conn.execute(
                    select(manifests)
                    .join(active, active.c.snapshot_id == manifests.c.snapshot_id)
                    .where(active.c.name == "specs")
                )
                .mappings()
                .first()
            )
        if not row:
            raise PolicyError("尚未发布 RAG 索引快照。")
        return dict(row)


_scope: ContextVar[dict | None] = ContextVar("rag_policy_scope", default=None)


@contextmanager
def request_scope(user_id: str, as_of: date | None = None):
    token = _scope.set({"user_id": user_id, "as_of": as_of, "manifest": None})
    try:
        yield
    finally:
        _scope.reset(token)


def scoped_query(where=None, collection_name=None):
    if not get_settings().rag_catalog_enabled:
        return where, collection_name
    scope = _scope.get()
    if scope is None:
        raise PolicyError("缺少服务端 RAG 身份上下文。")
    if scope["manifest"] is None:
        scope["manifest"] = Catalog().current()
    manifest = scope["manifest"]
    if collection_name and collection_name != manifest["collection_name"]:
        raise PolicyError("请求不能切换索引快照。")
    versions = select_versions(
        [VersionPolicy.model_validate(v) for v in manifest["payload"]["versions"]],
        scope["user_id"],
        scope["as_of"],
    )
    if not versions:
        raise PolicyError("没有已授权且符合指定日期的规范版本。")
    policy = {"version_id": {"$in": [v.version_id for v in versions]}}
    return ({"$and": [policy, where]} if where else policy), manifest["collection_name"]


def build_snapshot(
    chunks, policies: list[VersionPolicy], *, catalog=None, client=None, embedder=None
):
    """新集合完整构建后原子发布，不删除或覆盖旧索引。失败集合供管理员检查。"""
    from ..core.llm import get_embedding
    from .vector_store import get_client

    by_source = {p.source_doc: p for p in policies}
    if len(by_source) != len(policies) or len({p.version_id for p in policies}) != len(policies):
        raise ValueError("来源或版本 ID 重复")
    if {c.source_doc for c in chunks} != set(by_source) or not chunks:
        raise ValueError("每个来源必须有且只有一项显式版本/权限策略")
    if len({c.chunk_id for c in chunks}) != len(chunks):
        raise ValueError("chunk ID 必须唯一")
    s = get_settings()
    payload = {
        "versions": [p.model_dump(mode="json") for p in policies],
        "embedding_model": s.embedding_model,
        "embedding_dim": s.embedding_dim,
        "tokenizer": "jieba-0.42.1",
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "content_hash": hashlib.sha256(c.content.encode()).hexdigest(),
                "source_doc": c.source_doc,
                "section_number": c.section_number,
            }
            for c in chunks
        ],
    }
    identity = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    client, embedder, catalog = (
        client or get_client(),
        embedder or get_embedding(),
        catalog or Catalog(),
    )
    catalog.initialize()
    # 同一清单重复发布直接复用，避免重嵌入。
    with catalog.engine.connect() as conn:
        existing = (
            conn.execute(select(manifests).where(manifests.c.snapshot_id == identity))
            .mappings()
            .first()
        )
    if existing:
        collection = client.get_collection(existing["collection_name"])
        name = existing["collection_name"]
    else:
        name = f"rag_{identity[:16]}_{uuid.uuid4().hex[:8]}"
        collection = client.create_collection(
            name, metadata={"hnsw:space": "cosine", "snapshot_id": identity}
        )
        for start in range(0, len(chunks), 100):
            batch = chunks[start : start + 100]
            metadata = []
            for c in batch:
                p = by_source[c.source_doc]
                metadata.append(
                    {
                        **c.to_metadata(),
                        "version_id": p.version_id,
                        "document_id": p.document_id,
                        "version_status": p.status,
                        "effective_from": str(p.effective_from or ""),
                        "effective_to": str(p.effective_to or ""),
                        "snapshot_id": identity,
                    }
                )
            collection.upsert(
                ids=[c.chunk_id for c in batch],
                documents=[c.content for c in batch],
                metadatas=metadata,
                embeddings=embedder.embed_documents([c.content for c in batch]),
            )
    if collection.count() != len(chunks):
        raise ValueError("索引条数核对失败；旧索引保持活动")
    catalog.publish(identity, name, payload)
    return {"snapshot_id": identity, "collection_name": name, "chunks": len(chunks)}


def expand_references(docs: list[Document], *, max_extra: int = 4) -> list[Document]:
    from .vector_store import get_chunks

    result, seen = list(docs), {d.metadata["chunk_id"] for d in docs}
    for doc in docs:
        for section in dict.fromkeys(
            re.findall(r"(?:第\s*|见\s*|按\s*)(\d+(?:\.\d+)+)\s*条", doc.page_content)
        ):
            version = doc.metadata.get("version_id")
            if not version:
                continue
            refs = get_chunks(
                where={"$and": [{"version_id": version}, {"section_number": section}]}
            )
            additions = [r for r in refs if r.chunk_id not in seen]
            if not refs or len(result) + len(additions) > len(docs) + max_extra:
                raise PolicyError("明确引用条款缺失或超出证据预算，需人工核查。")
            for r in additions:
                seen.add(r.chunk_id)
                result.append(
                    Document(
                        page_content=r.content,
                        metadata={
                            **r.metadata,
                            "chunk_id": r.chunk_id,
                            "expanded_from": doc.metadata["chunk_id"],
                        },
                    )
                )
    return result
