"""core 包的单元测试。

只测纯逻辑（不发起真实 API 调用），保证脚手架可在无 .env 环境下也能跑测试。
"""

from __future__ import annotations

from petrochat.app.core import (
    AgentState,
    KnowledgeChunk,
    ScoreResult,
    get_settings,
)


def test_settings_loaded() -> None:
    """配置能成功加载，关键字段有合理默认值。"""
    s = get_settings()
    assert s.chroma_port == 8001
    assert s.embedding_dim == 1024
    assert s.deepseek_chat_model == "deepseek-chat"


def test_chroma_url_derivation() -> None:
    """chroma_url 派生属性正确拼接。"""
    s = get_settings()
    assert s.chroma_url == f"http://{s.chroma_host}:{s.chroma_port}"


def test_knowledge_chunk_to_metadata() -> None:
    """KnowledgeChunk 转 Chroma metadata 字段完整。"""
    chunk = KnowledgeChunk(
        chunk_id="test-1",
        content="测试内容",
        source_doc="设备变更管理程序",
        section_number="4.2.2",
        section_path="4 职责 > 4.2 设备主管部门",
        doc_code="SINOPEC-R&C-01-01",
        chunk_type="clause",
    )
    meta = chunk.to_metadata()
    assert meta["source_doc"] == "设备变更管理程序"
    assert meta["section_number"] == "4.2.2"
    assert meta["chunk_type"] == "clause"
    assert "created_at" in meta


def test_score_result_average() -> None:
    """三维评分平均值计算正确。"""
    score = ScoreResult(correctness=4, completeness=5, usefulness=3, reason="ok")
    assert score.average == 4.0


def test_agent_state_is_typeddict() -> None:
    """AgentState 是 TypedDict，可以用 dict 字面量构造。"""
    state: AgentState = {"question": "什么是 ITPM 策略？"}
    assert state["question"] == "什么是 ITPM 策略？"
