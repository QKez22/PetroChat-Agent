"""LangGraph 装配测试。

只测图结构 / 节点签名等离线可验证的部分，不发起真实 LLM 调用。
"""

from __future__ import annotations

from petrochat.app.agent import build_graph


def test_graph_builds() -> None:
    """图能成功编译。"""
    graph = build_graph()
    assert graph is not None


def test_graph_has_qa_node() -> None:
    """图含 qa 节点。"""
    graph = build_graph()
    # 编译后的 graph 暴露 nodes 属性（dict 形态）
    assert "qa" in graph.nodes


def test_graph_runnable_interface() -> None:
    """编译产物是 LangChain Runnable，含 invoke/stream 方法。"""
    graph = build_graph()
    assert hasattr(graph, "invoke")
    assert hasattr(graph, "stream")
    assert hasattr(graph, "astream")
