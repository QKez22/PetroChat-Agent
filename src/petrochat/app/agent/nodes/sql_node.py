"""SQL 节点（单步 NL2SQL）—— 数据查询专用。

跟 phase 2 的 query_database @tool 不同：
  - 这里不需要 LLM 决定"要不要调工具"——supervisor 已判定走 sql 分支
  - 直接调 nl2sql() 一步到位，更快、trace 更清晰
  - 输出 AIMessage 内嵌 Markdown 表 + 报表标记
  - 图表 base64 通过 report.pop_last_report() 由 SSE 层取走（侧信道）
"""

from __future__ import annotations

import pandas as pd
from langchain_core.messages import AIMessage
from loguru import logger

from ...core import AgentState
from ...report import render_report
from ...sql import nl2sql


def sql_node(state: AgentState) -> dict:
    """NL → SQL → 执行 → Markdown 表 + 图表（侧信道）。"""
    question = state.get("question", "").strip()
    if not question:
        return {"messages": [AIMessage(content="请提供问题。")]}

    result = nl2sql(question)

    if not result.ok:
        parts = [f"❌ 查询失败（阶段：{result.stage}）"]
        if result.sql:
            parts.append(f"**生成的 SQL:**\n```sql\n{result.sql}\n```")
        parts.append(f"**错误:** {result.error}")
        logger.warning("sql_node 失败: {}", result.error)
        return {"messages": [AIMessage(content="\n\n".join(parts))]}

    df = pd.DataFrame(result.rows, columns=result.columns)
    report = render_report(df, title=question, with_chart=True, max_rows=50)

    chart_note = ""
    if report.chart_data_uri:
        kind_zh = {"bar": "柱状图", "line": "折线图", "pie": "饼图"}.get(
            report.chart_kind, report.chart_kind
        )
        chart_note = f"\n\n📊 已生成{kind_zh}（前端可在 SSE meta 事件中接收）"

    content = (
        f"**SQL:**\n```sql\n{result.sql}\n```\n\n"
        f"**思路:** {result.reasoning}\n\n"
        f"**结果（{result.row_count} 行）:**\n{report.markdown}"
        f"{chart_note}"
    )
    return {"messages": [AIMessage(content=content)]}
