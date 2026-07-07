"""Memory routing, extraction trigger, and storage filtering policy."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

MemoryRoute = Literal["qa", "sql", "general", "memory"]

ALLOWED_MEMORY_TYPES = {
    "preference",
    "query_filter",
    "business_context",
    "historical_decision",
    "correction",
}
SQL_RECALL_TYPES = {"preference", "query_filter"}
QA_RECALL_TYPES = {"preference", "historical_decision", "correction"}
GENERAL_RECALL_TYPES = {"preference", "business_context", "historical_decision", "correction"}
MEMORY_RECALL_TYPES = ALLOWED_MEMORY_TYPES

_SQL_PAT = re.compile(
    r"(统计|数量|多少|清单|列表|事务|任务|部门|专业|到期|逾期|运行中|未完成|完成率|"
    r"count|quantity|list|task|department|active|overdue|due)",
    re.I,
)
_QA_PAT = re.compile(
    r"(规范|制度|条款|定义|什么是|流程|要求|标准|分级|职责|办法|文档|"
    r"standard|definition|clause|procedure|requirement|document)",
    re.I,
)
_MEMORY_PAT = re.compile(
    r"(记住|以后|今后|下次|默认|常用|偏好|我负责|我主要看|历史决策|项目偏好|固定条件|"
    r"remember|default|prefer|preference|project preference|historical decision|next time)",
    re.I,
)
_FOLLOWUP_PAT = re.compile(r"(刚才|上面|上一轮|这个|那个|继续|再按|再查|它|这些|其中)")
_SECRET_PAT = re.compile(r"(api[_-]?key|secret|token|password|密码|密钥|身份证|手机号|银行卡)", re.I)
_DOMAIN_FACT_PAT = re.compile(
    r"(规定|规范要求|条款|制度写明|标准要求|数据库结果|查询结果|SQL|SELECT|INSERT|UPDATE|DELETE)",
    re.I,
)
_LOW_VALUE_PAT = re.compile(r"^(你好|谢谢|好的|ok|嗯|啊|收到|帮我查一下|请回答|这个问题)$", re.I)


@dataclass(frozen=True)
class MemoryRecallPolicy:
    route: MemoryRoute
    memory_types: set[str]
    use_mem0: bool
    reason: str


@dataclass(frozen=True)
class AcceptedMemoryCandidate:
    memory_type: str
    content: str
    confidence: float
    metadata: dict


def infer_memory_route(question: str, route_hint: str | None = None) -> MemoryRoute:
    if route_hint in {"qa", "sql", "general"}:
        return route_hint  # type: ignore[return-value]
    text = question.strip()
    if _MEMORY_PAT.search(text):
        return "memory"
    if _SQL_PAT.search(text):
        return "sql"
    if _QA_PAT.search(text):
        return "qa"
    return "general"


def build_recall_policy(question: str, route_hint: str | None = None) -> MemoryRecallPolicy:
    route = infer_memory_route(question, route_hint=route_hint)
    if route == "sql":
        return MemoryRecallPolicy(
            route=route,
            memory_types=SQL_RECALL_TYPES,
            use_mem0=True,
            reason="NL2SQL only uses user preferences and query filters.",
        )
    if route == "qa":
        explicit_memory = bool(_MEMORY_PAT.search(question))
        return MemoryRecallPolicy(
            route=route,
            memory_types=QA_RECALL_TYPES,
            use_mem0=explicit_memory,
            reason="RAG answers use documents first; Mem0 is used only for explicit user context.",
        )
    if route == "memory":
        return MemoryRecallPolicy(
            route=route,
            memory_types=MEMORY_RECALL_TYPES,
            use_mem0=True,
            reason="The user explicitly asked about durable preferences or decisions.",
        )
    return MemoryRecallPolicy(
        route=route,
        memory_types=GENERAL_RECALL_TYPES,
        use_mem0=bool(_MEMORY_PAT.search(question)),
        reason="General chat uses session history first; long-term memory is limited to explicit context.",
    )


def should_extract_memory(question: str, answer: str = "", route: str | None = None) -> bool:
    text = f"{question}\n{answer}".strip()
    if len(text) < 12 or _LOW_VALUE_PAT.match(question.strip()):
        return False
    if _SECRET_PAT.search(text):
        return False
    if _MEMORY_PAT.search(text):
        return True
    if route == "sql" and any(
        word in question.lower()
        for word in ("默认", "常用", "以后", "筛选", "条件", "default", "prefer", "filter", "condition")
    ):
        return True
    return False


def is_followup_question(question: str) -> bool:
    return bool(_FOLLOWUP_PAT.search(question))


def classify_memory_type(content: str, route: str | None = None) -> str:
    text = content.strip()
    lower = text.lower()
    if any(word in lower for word in ("纠正", "不是", "更正", "以后不要", "correction", "correct", "do not")):
        return "correction"
    if any(word in lower for word in ("决定", "历史决策", "项目约定", "方案", "decision", "decided", "project rule")):
        return "historical_decision"
    if any(
        word in lower
        for word in ("默认", "筛选", "统计", "查询", "清单", "运行中", "到期", "default", "filter", "count", "active")
    ) or route == "sql":
        return "query_filter"
    if any(word in lower for word in ("我负责", "部门", "专业", "区域", "装置", "设备", "项目", "department", "project")):
        return "business_context"
    return "preference"


def accept_mem0_candidate(
    *,
    content: str,
    confidence: float,
    existing_contents: set[str],
    route: str | None = None,
    metadata: dict | None = None,
) -> AcceptedMemoryCandidate | None:
    normalized = _compact(content)
    if not normalized or len(normalized) < 8 or _LOW_VALUE_PAT.match(normalized):
        return None
    if _is_duplicate(normalized, existing_contents):
        return None
    memory_type = classify_memory_type(normalized, route=route)
    try:
        validate_memory_candidate(memory_type, normalized)
    except ValueError:
        return None
    return AcceptedMemoryCandidate(
        memory_type=memory_type,
        content=normalized,
        confidence=max(0.0, min(confidence or 0.75, 1.0)),
        metadata={
            "extractor": "mem0_infer",
            "stage": "accepted",
            "route": route or "unknown",
            **(metadata or {}),
        },
    )


def validate_memory_candidate(memory_type: str, content: str) -> None:
    normalized_type = memory_type.strip()
    normalized_content = content.strip()
    if normalized_type not in ALLOWED_MEMORY_TYPES:
        raise ValueError(f"unsupported memory_type: {memory_type}")
    if _SECRET_PAT.search(normalized_content):
        raise ValueError("sensitive credentials or personal secrets cannot be stored as long-term memory")
    if normalized_type not in {"correction", "historical_decision"} and _DOMAIN_FACT_PAT.search(normalized_content):
        raise ValueError("domain facts, SQL results, and document facts must not be stored as user memory")


def _is_duplicate(content: str, existing_contents: set[str]) -> bool:
    compact_existing = {_compact(item) for item in existing_contents}
    if content in compact_existing:
        return True
    return any(SequenceMatcher(a=content, b=item).ratio() >= 0.9 for item in compact_existing)


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())
