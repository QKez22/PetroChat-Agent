"""从用户消息维护当前有效约束, 修改同类条件时覆盖旧值。"""

from __future__ import annotations

import hashlib
import json
import re


def active_constraints(
    history: list[dict], question: str = "", initial: dict | None = None
) -> dict[str, str]:
    from ..sql.contract import extract_contract

    slots: dict[str, str] = dict(initial or {})
    for item in [*history, {"role": "user", "content": question}]:
        if item.get("role") != "user":
            continue
        text = item.get("content", "")
        if re.search(r"换个话题|另一个问题|重新开始|清空条件", text):
            slots.clear()
        contract = extract_contract(text)
        for key in ("entity", "groups", "times", "strategy", "top"):
            if contract.get(key):
                slots[key] = json.dumps(contract[key], ensure_ascii=False)
        for key, value in contract.get("filters", {}).items():
            slots[key] = json.dumps(value, ensure_ascii=False)
        if re.search(r"不限部门|所有部门|取消部门筛选", text):
            slots.pop("departments", None)
        if re.search(r"不分组|只要总数|取消分组", text):
            slots.pop("groups", None)
        if re.search(r"不(?:要|含|包括)|排除|除了", text):
            slots["negation"] = text
        # 不认识的强约束保留原文, 不因无法解析成部门/时间槽位而被摘要丢弃。
        if re.search(r"不得|不能|不超过|不少于|必须|至少|至多", text):
            key = "unresolved:" + hashlib.sha256(text.encode()).hexdigest()[:12]
            slots[key] = "[未结构化约束; 有冲突时需确认] " + text
    return slots


def constraints_text(slots: dict[str, str]) -> str:
    if not slots:
        return ""
    return (
        "【当前用户约束; 当前消息优先, 不得按旧条件覆盖】\n"
        + "\n".join(f"- {key}: {value}" for key, value in slots.items())
        + "\n[END_CONSTRAINTS]"
    )


def stored_constraints(summary: str) -> dict:
    for line in summary.splitlines():
        if line.startswith("CONSTRAINTS_V1="):
            try:
                value = json.loads(line.split("=", 1)[1])
                if isinstance(value, dict) and all(
                    isinstance(k, str) and isinstance(v, str) for k, v in value.items()
                ):
                    return value
            except ValueError:
                pass
    return {}
