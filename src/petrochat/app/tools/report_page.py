"""大报表按页回读; 数据只存在于当前请求预算上下文, 不进入全局缓存。"""

from __future__ import annotations

import hashlib
import json

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool

from ..core.budget import current_budget


def compact_report_messages(messages: list) -> list:
    budget = current_budget()
    if budget is None:
        return messages
    result = []
    for message in messages:
        data = (
            message.artifact.get("query_result")
            if isinstance(message, ToolMessage) and isinstance(message.artifact, dict)
            else None
        )
        if not data or len(data.get("rows", [])) <= 5:
            result.append(message)
            continue
        ref = hashlib.sha256(
            (message.tool_call_id + json.dumps(data, ensure_ascii=False, default=str)).encode()
        ).hexdigest()[:16]
        with budget.lock:
            budget.report_cache[ref] = data
        preview = {
            "report_id": ref,
            "columns": data["columns"],
            "row_count": len(data["rows"]),
            "sql": data["sql"],
            "preview_rows": data["rows"][:5],
            "complete": False,
            "notice": "这里只展示前5行。需要其余行时用 read_report_page; 不得把预览当作全量统计。",
        }
        result.append(
            message.model_copy(
                update={"content": json.dumps(preview, ensure_ascii=False, default=str)}
            )
        )
    return result


@tool
def read_report_page(report_id: str, offset: int = 0, page_size: int = 20) -> str:
    """按页读取本次工具查询的原始行, report_id 来自工具预览。"""
    budget = current_budget()
    if not budget or report_id not in budget.report_cache:
        return "❌ 报表不属于当前请求或已过期。"
    budget.check()
    if offset < 0 or not 1 <= page_size <= 50:
        return "❌ offset 必须非负, page_size 必须在1到50之间。"
    data = budget.report_cache[report_id]
    rows = data["rows"][offset : offset + page_size]
    return json.dumps(
        {
            "report_id": report_id,
            "columns": data["columns"],
            "rows": rows,
            "total_rows": len(data["rows"]),
            "offset": offset,
            "has_more": offset + len(rows) < len(data["rows"]),
        },
        ensure_ascii=False,
        default=str,
    )
