"""Pydantic 实体模型。

跟 state.py 的 TypedDict 互补：
  - TypedDict 用于 LangGraph 内部高频读写、节点间传递
  - Pydantic 用于 API 边界、LLM 结构化输出、持久化对象
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class KnowledgeChunk(BaseModel):
    """向量库中的一条知识片段。

    入库前组装、检索后还原都用这个模型，保证字段命名贯穿整个 RAG pipeline。
    """

    chunk_id: str = Field(description="唯一标识，由 source_doc + section_number 派生")
    content: str = Field(description="片段正文")
    source_doc: str = Field(description="所属规范文件名（不含扩展名）")
    section_number: str = Field(default="", description="章节编号，如 4.2.2")
    section_path: str = Field(default="", description="章节路径，如 '4 职责 > 4.2 设备主管部门'")
    doc_code: str = Field(default="", description="文档代号，如 SINOPEC-R&C-01-01")
    chunk_type: Literal["clause", "table", "definition", "other"] = Field(
        default="clause", description="片段类型，便于检索时过滤"
    )
    created_at: datetime = Field(default_factory=datetime.now)

    def to_metadata(self) -> dict[str, str]:
        """转成 Chroma metadata 字典（Chroma 要求 metadata 值是 str/int/float/bool）。"""
        return {
            "source_doc": self.source_doc,
            "section_number": self.section_number,
            "section_path": self.section_path,
            "doc_code": self.doc_code,
            "chunk_type": self.chunk_type,
            "created_at": self.created_at.isoformat(),
        }


class RetrievedChunk(BaseModel):
    """检索后的单条结果，包含相似度得分。"""

    chunk_id: str
    content: str
    metadata: dict[str, str | int | float | bool]
    score: float = Field(description="相似度得分，越接近 0（cosine distance）越相关")


class ScoreResult(BaseModel):
    """三维质检评分结果（第四阶段使用，第一阶段先定义类型）。"""

    correctness: int = Field(ge=1, le=5, description="正确性 1-5")
    completeness: int = Field(ge=1, le=5, description="完整性 1-5")
    usefulness: int = Field(ge=1, le=5, description="有用性 1-5")
    reason: str = Field(description="评分理由")

    @property
    def average(self) -> float:
        """三维平均分，可用于判断是否触发重试。"""
        return (self.correctness + self.completeness + self.usefulness) / 3


# ---------- API 边界模型 ----------


class ChatRequest(BaseModel):
    """前端 → 后端的对话请求。"""

    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, description="多轮会话 ID")
    user_id: str = Field(default="default", min_length=1, max_length=64)


class ChatResponse(BaseModel):
    """非流式接口的响应（流式接口用 SSE，不走这个）。"""

    answer: str
    citations: list[str] = Field(default_factory=list)
    score: ScoreResult | None = None
    session_id: str | None = None
    memory_used: list[str] = Field(default_factory=list)
    memory_written: list[str] = Field(default_factory=list)
    memory_recall: dict = Field(default_factory=dict)


class SessionSummary(BaseModel):
    """会话列表项。"""

    id: str
    user_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


class ChatMessageRecord(BaseModel):
    """持久化后的单条消息。"""

    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    route: str | None = None
    latency_ms: int | None = None
    created_at: str


class SessionDetail(BaseModel):
    """会话详情。"""

    session: SessionSummary
    messages: list[ChatMessageRecord]


class LoginRequest(BaseModel):
    """登录请求。

    当前阶段按项目约束先使用明文密码，并由前端保存本地 token。
    """

    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class AuthUser(BaseModel):
    """登录后的用户与角色信息。"""

    user_id: str
    username: str
    role: Literal["admin", "engineer"]
    authority_flag: int
    permissions: list[str] = Field(default_factory=list)


class LoginResponse(BaseModel):
    """登录响应。

    token 是前端本地演示 token，不作为生产级鉴权凭据。
    """

    token: str
    user: AuthUser
