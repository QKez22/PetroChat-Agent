"""只整理本轮 worker 产出, 两种接口和评估共用相同答案口径。"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from ..core.models import TurnResult

CITATION_PATTERN = re.compile(r"\[(\d+(?:\.\d+){1,3})\]")


def answer_parts(messages: list) -> list[str]:
    """忽略历史轮次、工具调用前言和非文本内容。"""
    start = next(
        (i + 1 for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)),
        0,
    )
    parts = []
    for message in messages[start:]:
        if not isinstance(message, AIMessage) or message.tool_calls:
            continue
        content = message.content
        if isinstance(content, list):
            content = "".join(
                block if isinstance(block, str) else block.get("text", "")
                for block in content
                if isinstance(block, str) or (isinstance(block, dict) and block.get("type") == "text")
            )
        if content and content.strip():
            parts.append(content.strip())
    return parts


def build_turn_result(state: dict[str, Any]) -> TurnResult:
    messages = state.get("messages") or []
    answer = "\n\n".join(answer_parts(messages))
    artifacts = list(state.get("artifacts") or [])
    start = next(
        (i + 1 for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)),
        0,
    )
    for message in messages[start:]:
        if isinstance(message, ToolMessage) and isinstance(message.artifact, dict):
            artifacts.extend(message.artifact.get("reports") or [])
    return TurnResult(
        answer=answer,
        citations=list(dict.fromkeys(CITATION_PATTERN.findall(answer))),
        artifacts=artifacts,
    )
