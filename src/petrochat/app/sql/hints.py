"""Business filter hints for NL2SQL prompts.

The hints are deterministic guardrails, not a replacement for SQL validation.
They help the LLM inherit short-term SQL constraints in multi-turn questions
such as "只看频次是 1次/季度 的" after an equipment/task query.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_EQUIPMENT_ID_PAT = re.compile(r"(?<![A-Z0-9])[A-Z]{1,3}\d{2,5}(?:-[A-Z0-9]+)?(?![A-Z0-9])", re.I)
_FREQUENCY_PAT = re.compile(r"\d+\s*次\s*/\s*[\u4e00-\u9fffA-Za-z0-9]+")
_AFFAIR_NAME_PATS = (
    re.compile(r"相关的?(?P<name>[\u4e00-\u9fffA-Za-z0-9/-]{2,40}?)(?:任务|事务|措施)"),
    re.compile(r"未指定的(?P<name>[\u4e00-\u9fffA-Za-z0-9/-]{2,40}?)(?:任务|事务|措施)"),
)

_DEPARTMENT_VALUES = (
    "炼油一部",
    "炼油二部",
    "炼油三部",
    "炼油四部",
    "炼油公用工程部",
    "化工公用工程部",
    "烯烃部",
    "储运部",
    "动力部",
    "环氧芳烃部",
    "聚烯烃一部",
    "聚烯烃二部",
    "检验计量中心",
    "设备工程部",
)

_SPECIALTY_HINTS = (
    ("仪表", "仪"),
    ("仪控", "仪"),
    ("动设备", "动"),
    ("转动设备", "动"),
    ("静设备", "静"),
    ("电气", "电"),
    ("综合", "综合"),
)

_SPECIALTY_KEYWORD_HINTS: dict[str, tuple[str, ...]] = {
    "动": (
        "大机组",
        "机组",
        "润滑油泵",
        "泵",
        "蒸汽透平",
        "透平",
        "速关阀",
        "压缩机",
        "风机",
        "汽轮机",
    ),
}

_TASK_INTENT_WORDS = (
    "任务",
    "措施",
    "执行",
    "设备",
    "位号",
    "检修",
    "巡检",
    "统计",
    "频次",
)


@dataclass
class SqlBusinessHints:
    """Structured hints extracted from current and recent user turns."""

    recent_user_questions: list[str] = field(default_factory=list)
    departments: list[str] = field(default_factory=list)
    specialties: list[str] = field(default_factory=list)
    affair_names: list[str] = field(default_factory=list)
    frequencies: list[str] = field(default_factory=list)
    equipment_ids: list[str] = field(default_factory=list)
    prefer_task_table: bool = False

    def has_hints(self) -> bool:
        return bool(
            self.recent_user_questions
            or self.departments
            or self.specialties
            or self.affair_names
            or self.frequencies
            or self.equipment_ids
            or self.prefer_task_table
        )


def build_sql_question_with_hints(
    question: str,
    *,
    history: list[dict[str, Any]] | None = None,
    long_term_context: str = "",
) -> str:
    """Wrap the question with short-term SQL constraints and filter hints."""

    hints = extract_sql_business_hints(question, history=history)
    if not hints.has_hints() and not long_term_context.strip():
        return question

    sections = ["【当前问题】", question.strip()]
    if hints.recent_user_questions:
        sections.extend([
            "",
            "【最近用户约束】",
            *[f"- {item}" for item in hints.recent_user_questions],
            "说明：如果当前问题是补充筛选、统计或追问，必须继承这些约束；只有用户明确改条件时才覆盖。",
        ])

    filter_lines = _render_filter_lines(hints)
    if filter_lines:
        sections.extend(["", "【SQL过滤提示】", *filter_lines])

    if long_term_context.strip():
        sections.extend(["", "【长期记忆约束】", long_term_context.strip()])

    return "\n".join(sections)


def extract_sql_business_hints(
    question: str,
    *,
    history: list[dict[str, Any]] | None = None,
    max_recent_user_turns: int = 3,
) -> SqlBusinessHints:
    history = history or []
    recent_users = _recent_user_messages(history, max_recent_user_turns)
    combined = "\n".join([*recent_users, question])

    hints = SqlBusinessHints(recent_user_questions=recent_users)
    hints.departments = _ordered_unique(
        dept for dept in _DEPARTMENT_VALUES if dept in combined
    )
    hints.specialties = _ordered_unique(
        [
            *(value for label, value in _SPECIALTY_HINTS if label in combined),
            *(
                value
                for value, keywords in _SPECIALTY_KEYWORD_HINTS.items()
                if any(keyword in combined for keyword in keywords)
            ),
        ]
    )
    hints.affair_names = _ordered_unique(
        _normalise_affair_name(match.group("name"))
        for pattern in _AFFAIR_NAME_PATS
        for match in pattern.finditer(combined)
    )
    hints.frequencies = _ordered_unique(
        _normalise_frequency(item) for item in _FREQUENCY_PAT.findall(combined)
    )
    hints.equipment_ids = _ordered_unique(
        item.upper() for item in _EQUIPMENT_ID_PAT.findall(combined)
    )
    hints.prefer_task_table = any(word in combined for word in _TASK_INTENT_WORDS)
    return hints


def _render_filter_lines(hints: SqlBusinessHints) -> list[str]:
    lines: list[str] = []
    if hints.prefer_task_table:
        lines.append(
            "- 涉及任务、设备、位号、检修、巡检、执行情况或频次统计时，优先以 `affair_task` 为主表。"
        )
    if hints.departments:
        values = " / ".join(hints.departments)
        lines.append(f"- 运行部过滤：优先使用 `affair_task.operation_department` LIKE '%{values}%'。")
    if hints.specialties:
        values = " / ".join(hints.specialties)
        lines.append(f"- 专业过滤：必须写入 WHERE `affair_task.specialty`，枚举值为 {values}。")
    if hints.affair_names:
        values = " / ".join(hints.affair_names)
        lines.append(
            "- 事务名称过滤：优先使用 `affair_task.affair_name` 或 `affair_task.task_name`，"
            f"必须保留完整短语 {values}，不要只拆成局部关键词。"
        )
    if hints.frequencies:
        values = " / ".join(hints.frequencies)
        lines.append(f"- 频次过滤：使用 `affair_task.frequency`，值为 {values}。")
    if hints.equipment_ids:
        values = " / ".join(hints.equipment_ids)
        lines.append(
            "- 设备位号/编码过滤：优先匹配 `affair_task.technical_id_code`，"
            f"必要时再 OR `body_equipment_code`/`task_equipment_code`；值为 {values}。"
            "如果位号包含短横线，必须完整保留，不要截断。"
        )
    if hints.prefer_task_table:
        lines.append(
            "- 若需要事务字段，使用关联键 "
            "`affair_task.associated_affair_id = affair.affair_id`，不要丢失 task 表过滤条件。"
        )
    return lines


def _recent_user_messages(history: list[dict[str, Any]], limit: int) -> list[str]:
    users: list[str] = []
    for item in reversed(history):
        if item.get("role") != "user":
            continue
        content = str(item.get("content") or "").strip()
        if content:
            users.append(content)
        if len(users) >= limit:
            break
    return list(reversed(users))


def _normalise_frequency(value: str) -> str:
    text = value.replace(" ", "").strip()
    for suffix in ("的", "地", "。", "，", ",", "；", ";"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text


def _normalise_affair_name(value: str) -> str:
    text = value.strip(" 的。？，,；;：:")
    return text


def _ordered_unique(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
