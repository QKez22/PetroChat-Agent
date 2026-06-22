"""LangGraph 全局状态对象。

设计要点：
1. 用 TypedDict 而非 Pydantic：LangGraph 对 TypedDict 原生友好，节点返回 dict 自动合并。
2. 第一阶段就定义完整字段（含后续阶段需要的 score / next 等），后续节点只用不改字段定义。
3. 路由字段 `next` 用 Literal 严格约束，避免 LLM 自由发挥污染状态机。
4. 集合类字段（retrieved / citations / messages）默认值由节点初始化，不在类型里强制写死。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

# ---- 路由出口字面量 ----
# 给 supervisor / 条件边使用：节点返回 `next` 字段时只能是这些值之一
NextNode = Literal["qa", "tool", "scoring", "FINISH"]


class AgentState(TypedDict, total=False):
    """LangGraph 节点间共享的状态对象。

    所有字段都标记为 total=False（可选），节点按需写入：
      - 入口（API 层）只需提供 question
      - qa 节点写入 retrieved / answer / citations
      - scoring 节点写入 score
      - supervisor 写入 next

    特殊字段说明：
      - messages：用 add_messages reducer，多个节点 append 消息时自动合并去重
      - retrieved：保留原始召回片段（含 score 和 metadata），便于调试和 UI 展示
      - retry_count：评分过低重试的计数器，触发循环熔断
    """

    # ---------- 输入 ----------
    question: str
    """用户原始问题。"""

    # ---------- 对话历史（多轮 / 流式）----------
    messages: Annotated[list[BaseMessage], add_messages]
    """LangChain 消息列表；用 add_messages reducer 累积。"""

    # ---------- RAG 阶段产物 ----------
    retrieved: list[dict[str, Any]]
    """召回的知识片段，每个 dict 含 content / metadata / score 字段。"""

    answer: str
    """LLM 生成的最终答案文本。"""

    citations: list[str]
    """引用来源标识（如 "设备变更管理程序 4.2.2"），与 retrieved 对应。"""

    # ---------- 评分（第四阶段）----------
    score: dict[str, Any]
    """三维评分结果：{"correctness": 4, "completeness": 5, "usefulness": 4, "reason": "..."}"""

    # ---------- 路由（多 Agent 阶段）----------
    intent: str
    """识别出的用户意图，如 "knowledge_qa" / "tool_call" 等。"""

    next: NextNode
    """下一个要路由到的节点；FINISH 表示终止图。"""

    # ---------- 控制 ----------
    retry_count: int
    """评分过低重试次数，由 supervisor 维护，超过上限强制 FINISH 避免死循环。"""
