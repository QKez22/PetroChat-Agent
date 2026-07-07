"""Conversation rolling-summary and pruning utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass

from loguru import logger

from ..core import get_settings
from .store import ConversationStore, ConversationSummary, StoredMessage, get_conversation_store

_FOLLOWUP_PAT = re.compile(r"(刚才|上面|上一轮|这个|那个|继续|再按|再查|它|这些|其中)")
_ENTITY_PAT = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_\-]{2,}")
_CODE_OR_TOOL_PAT = re.compile(r"```|<tool|tool_result|Traceback|SELECT\s+.+FROM", re.I | re.S)


@dataclass(frozen=True)
class SummaryUpdateResult:
    summary: ConversationSummary | None
    updated: bool
    pruned_message_count: int
    trigger_reasons: list[str] | None = None


@dataclass(frozen=True)
class PromptContextBudgetResult:
    history: list[dict]
    conversation_summary: str
    long_term_context: str
    estimated_tokens: int
    dropped_history_count: int


def refresh_conversation_summary(
    conversation_id: str,
    *,
    store: ConversationStore | None = None,
    force: bool = False,
) -> SummaryUpdateResult:
    """Summarize messages outside the recent raw window.

    Raw messages stay in MySQL. Only prompt context is pruned into a rolling
    summary, so no original conversation data is lost.
    """

    settings = get_settings()
    if not settings.conversation_summary_enabled and not force:
        return SummaryUpdateResult(summary=None, updated=False, pruned_message_count=0)

    store = store or get_conversation_store()
    try:
        messages = store.list_messages(conversation_id, limit=500)
        current = store.get_summary(conversation_id)
    except Exception as exc:
        logger.warning("conversation summary pre-read failed: {}", exc)
        return SummaryUpdateResult(summary=None, updated=False, pruned_message_count=0)

    raw_window = _raw_window_message_count(settings.short_term_turns)
    if len(messages) <= raw_window:
        return SummaryUpdateResult(summary=current, updated=False, pruned_message_count=0)

    window_before_recent = messages[:-raw_window]
    candidate_messages = _candidate_summary_messages(window_before_recent, current)
    if not candidate_messages:
        return SummaryUpdateResult(summary=current, updated=False, pruned_message_count=0)

    should_update, reasons = _should_refresh_summary(
        messages=messages,
        candidate_messages=candidate_messages,
        force=force,
    )
    if not should_update:
        return SummaryUpdateResult(summary=current, updated=False, pruned_message_count=0, trigger_reasons=reasons)

    summary_text = build_conversation_summary(
        previous_summary=current.summary_text if current else "",
        messages=candidate_messages,
        max_chars=_summary_max_chars(),
    )
    try:
        summary = store.upsert_summary(
            conversation_id,
            summary_text=summary_text,
            summarized_until_message_id=candidate_messages[-1].id,
            source_message_count=(current.source_message_count if current else 0) + len(candidate_messages),
        )
    except Exception as exc:
        logger.warning("conversation summary upsert failed: {}", exc)
        return SummaryUpdateResult(summary=current, updated=False, pruned_message_count=0)
    return SummaryUpdateResult(
        summary=summary,
        updated=True,
        pruned_message_count=len(candidate_messages),
        trigger_reasons=reasons,
    )


def build_conversation_summary(
    *,
    previous_summary: str,
    messages: list[StoredMessage],
    max_chars: int,
) -> str:
    facts = _extract_summary_facts(messages)
    sections = [
        ("已确认事实", [*facts["constraints"], *facts["entities"], *facts["results"]], 5),
        ("当前任务目标", facts["goals"], 3),
        ("用户偏好", facts["preferences"], 3),
        ("未解决问题", facts["open_items"], 3),
    ]
    lines: list[str] = []
    lines.append("【会话摘要】")
    if previous_summary.strip():
        lines.extend(_clip_lines(previous_summary.splitlines(), max_lines=8))
    for title, values, limit in sections:
        kept = _dedupe(values)[:limit]
        if not kept:
            continue
        lines.append(f"{title}:")
        lines.extend(f"- {item}" for item in kept)
    return _prune_summary("\n".join(lines), max_chars=max(300, max_chars))


def build_conversation_summary_message(summary: str) -> str:
    if not summary.strip():
        return ""
    return (
        "会话滚动摘要\n"
        "[Conversation rolling summary]\n"
        "Older turns were compressed to control prompt length. Treat this as session context, "
        "not as durable user memory.\n"
        f"{summary}"
    )


def _extract_summary_facts(messages: list[StoredMessage]) -> dict[str, list[str]]:
    facts = {
        "goals": [],
        "constraints": [],
        "entities": [],
        "preferences": [],
        "results": [],
        "open_items": [],
    }
    for msg in messages:
        text = _compact(msg.content)
        if not text:
            continue
        preview = _clip(text, 160)
        if msg.role == "user":
            facts["goals"].append(preview)
            if any(word in text for word in ("默认", "筛选", "条件", "只看", "按", "default", "filter")):
                facts["constraints"].append(preview)
            if any(word in text for word in ("偏好", "习惯", "以后", "默认", "喜欢", "prefer", "default")):
                facts["preferences"].append(preview)
            if _FOLLOWUP_PAT.search(text):
                facts["open_items"].append(preview)
        else:
            facts["results"].append(preview)
        facts["entities"].extend(_important_entities(text))
    return facts


def fit_prompt_context(
    *,
    question: str,
    history: list[dict],
    conversation_summary: str,
    long_term_context: str,
) -> PromptContextBudgetResult:
    """Fit prompt-side context into the application-level token budget.

    This does not delete database history. It only decides what is injected into
    the current prompt.
    """

    settings = get_settings()
    summary = prune_text_to_tokens(conversation_summary, settings.conversation_summary_max_tokens)
    memory_context = prune_text_to_tokens(long_term_context, max(settings.long_term_memory_limit, 1) * 180)
    kept_history = list(history)
    budget = _input_token_budget()
    dropped = 0
    estimated = _estimate_prompt_tokens(question, kept_history, summary, memory_context)
    while kept_history and estimated > budget:
        kept_history.pop(0)
        dropped += 1
        estimated = _estimate_prompt_tokens(question, kept_history, summary, memory_context)
    if estimated > budget and summary:
        remaining = max(200, budget - _estimate_prompt_tokens(question, kept_history, "", memory_context))
        summary = prune_text_to_tokens(summary, remaining)
        estimated = _estimate_prompt_tokens(question, kept_history, summary, memory_context)
    return PromptContextBudgetResult(
        history=kept_history,
        conversation_summary=summary,
        long_term_context=memory_context,
        estimated_tokens=estimated,
        dropped_history_count=dropped,
    )


def estimate_tokens(text: str) -> int:
    """Conservative token estimate for mixed Chinese/English prompt budgeting."""

    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    ascii_chars = len(text) - cjk
    return max(1, cjk + ascii_chars // 4)


def prune_text_to_tokens(text: str, max_tokens: int) -> str:
    if estimate_tokens(text) <= max_tokens:
        return text
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    kept: list[str] = []
    total = 0
    for line in reversed(lines):
        tokens = estimate_tokens(line)
        if total + tokens > max_tokens:
            continue
        kept.append(line)
        total += tokens
    if kept:
        return "\n".join(reversed(kept))
    max_chars = max(200, max_tokens * 2)
    return text[:max_chars]


def _important_entities(text: str) -> list[str]:
    stop = {"请", "帮我", "这个", "那个", "统计", "查询", "列表", "结果", "answer", "task"}
    entities = []
    for token in _ENTITY_PAT.findall(text):
        if token.lower() in stop or len(token) > 40:
            continue
        if any(ch.isdigit() for ch in token) or any("\u4e00" <= ch <= "\u9fff" for ch in token):
            entities.append(token)
    return entities[:8]


def _prune_summary(summary: str, *, max_chars: int) -> str:
    lines = _dedupe([line.strip() for line in summary.splitlines() if line.strip()])
    output: list[str] = []
    total = 0
    for line in reversed(lines):
        line_len = len(line) + 1
        if total + line_len > max_chars:
            continue
        output.append(line)
        total += line_len
    return "\n".join(reversed(output))


def _raw_window_message_count(short_term_turns: int) -> int:
    return max(short_term_turns, 1) * 2


def _candidate_summary_messages(
    window_before_recent: list[StoredMessage],
    current: ConversationSummary | None,
) -> list[StoredMessage]:
    pointer = _safe_int(current.summarized_until_message_id if current else None)
    if pointer is None:
        return window_before_recent
    return [msg for msg in window_before_recent if _safe_int(msg.id) is not None and int(msg.id) > pointer]


def _should_refresh_summary(
    *,
    messages: list[StoredMessage],
    candidate_messages: list[StoredMessage],
    force: bool,
) -> tuple[bool, list[str]]:
    if force:
        return True, ["force"]
    settings = get_settings()
    reasons: list[str] = []
    pending_count = len(candidate_messages)
    if pending_count >= max(settings.conversation_summary_min_pending_messages, 1):
        reasons.append("pending_batch")
    if pending_count >= max(settings.conversation_summary_trigger_turns, 1) * 2:
        reasons.append("turn_distance")
    estimated = estimate_tokens("\n".join(msg.content for msg in messages))
    if estimated >= int(_input_token_budget() * settings.conversation_summary_trigger_token_ratio):
        reasons.append("token_budget")
    if any(_is_long_or_tool_heavy_message(msg) for msg in candidate_messages):
        reasons.append("long_tool_or_code")
    if _topic_shift_detected(messages):
        reasons.append("topic_shift")
    return bool(reasons), reasons


def _is_long_or_tool_heavy_message(msg: StoredMessage) -> bool:
    settings = get_settings()
    return estimate_tokens(msg.content) >= settings.conversation_summary_long_message_tokens or bool(
        _CODE_OR_TOOL_PAT.search(msg.content)
    )


def _topic_shift_detected(messages: list[StoredMessage]) -> bool:
    user_messages = [msg.content for msg in messages if msg.role == "user"]
    if len(user_messages) < 2:
        return False
    latest = set(_ENTITY_PAT.findall(user_messages[-1]))
    previous = set(_ENTITY_PAT.findall(user_messages[-2]))
    if not latest or not previous:
        return False
    overlap = len(latest & previous) / max(len(latest), 1)
    switch_words = ("换个话题", "另一个问题", "先不说", "回到", "接下来", "另外")
    return overlap < 0.2 or any(word in user_messages[-1] for word in switch_words)


def _estimate_prompt_tokens(
    question: str,
    history: list[dict],
    conversation_summary: str,
    long_term_context: str,
) -> int:
    history_text = "\n".join(str(item.get("content") or "") for item in history)
    settings = get_settings()
    return (
        settings.context_system_token_budget
        + estimate_tokens(question)
        + estimate_tokens(history_text)
        + estimate_tokens(conversation_summary)
        + estimate_tokens(long_term_context)
    )


def _input_token_budget() -> int:
    settings = get_settings()
    model_budget = max(settings.context_window_tokens - settings.context_output_token_reserve, 256)
    return max(256, min(settings.context_input_token_budget, model_budget))


def _summary_max_chars() -> int:
    settings = get_settings()
    return min(settings.conversation_summary_max_chars, settings.conversation_summary_max_tokens * 4)


def _safe_int(value: str | int | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _clip_lines(lines: list[str], *, max_lines: int) -> list[str]:
    return [line for line in lines if line.strip()][-max_lines:]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _compact(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "..."


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())
