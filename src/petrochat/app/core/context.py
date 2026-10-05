"""在最终 SDK 请求上检查上下文, 不截断当前需求、约束和工具调用配对。"""

from __future__ import annotations

import copy
import json
import re

from langchain_openai import ChatOpenAI

from .budget import BudgetExceeded, current_budget, model_run_id
from .config import get_settings


def estimate_payload(payload: dict) -> int:
    # 包含工具/schema 定义和消息协议开销。估算不是供应商精确 tokenizer。
    text = json.dumps(
        {k: payload[k] for k in ("messages", "tools", "response_format") if k in payload},
        ensure_ascii=False,
    )
    cjk = sum("\u4e00" <= c <= "\u9fff" for c in text)
    return cjk + (len(text) - cjk + 2) // 3 + 64


def prepare_payload(payload: dict) -> tuple[dict, dict]:
    result = copy.deepcopy(payload)
    settings = get_settings()
    cap = min(
        settings.context_input_token_budget,
        settings.context_window_tokens - settings.context_output_token_reserve,
    )
    before = estimate_payload(result)
    messages = result.get("messages", [])
    latest = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=-1)
    followup = (
        bool(
            re.search(
                r"刚才|上面|这些|其中|继续|它|上一|那个|previous|above",
                str(messages[latest].get("content", "")),
            )
        )
        if latest >= 0
        else True
    )
    removed = 0
    # 只清理独立新问题前的旧 assistant 解释。用户条件、系统消息、工具配对全部保护。
    if not followup:
        for i, message in enumerate(messages):
            if estimate_payload(result) <= cap:
                break
            if i < latest and message.get("role") == "assistant" and not message.get("tool_calls"):
                message["content"] = "[旧回答未注入本次上下文; 不可据此推断历史结果]"
                removed += 1
    after = estimate_payload(result)
    stats = {
        "input_estimated_before": before,
        "input_estimated_after": after,
        "input_limit": cap,
        "old_answers_removed": removed,
        "context_rejected": after > cap,
    }
    if budget := current_budget():
        budget.update_model_stats(model_run_id.get(), stats)
    if after > cap:
        reason = "上下文核心内容超过输入预算，请缩小问题或资料范围"
        if budget := current_budget():
            budget.stop(reason)
        raise BudgetExceeded(reason)
    return result, stats


class ContextChatOpenAI(ChatOpenAI):
    """覆盖绑定工具、结构化输出、同步/异步与 streaming 共用的最终请求入口。"""

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        return prepare_payload(payload)[0]
