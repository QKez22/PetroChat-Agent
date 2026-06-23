"""query_database 工具：让 ReAct agent 能查 MySQL 业务库 + 自动生成报表。

Step 4.3 接入 report 模块：
- DataFrame → Markdown 表 + base64 图表
- 给 LLM 的字符串里不带 base64（省 token），只标注"已生成图表"
- 图表通过 report.pop_last_report() 由 SSE 层取走作 meta 事件
"""

from __future__ import annotations

import pandas as pd
from langchain_core.tools import tool

from ..report import render_report
from ..sql import nl2sql


@tool
def query_database(question: str) -> str:
    """查询事务任务管理 MySQL 数据库（affair 事务表 / affair_task 任务表）。

    Args:
        question: 用户的自然语言问题（中文）

    Returns:
        Markdown 字符串：含 SQL、推理、结果表格、图表标记。
    """
    result = nl2sql(question)

    if not result.ok:
        parts = [f"❌ 查询失败（阶段：{result.stage}）"]
        if result.sql:
            parts.append(f"**生成的 SQL:**\n```sql\n{result.sql}\n```")
        parts.append(f"**错误:** {result.error}")
        return "\n\n".join(parts)

    df = pd.DataFrame(result.rows, columns=result.columns)
    report = render_report(df, title=question, with_chart=True, max_rows=50)

    chart_note = ""
    if report.chart_data_uri:
        kind_zh = {"bar": "柱状图", "line": "折线图", "pie": "饼图"}.get(
            report.chart_kind, report.chart_kind
        )
        chart_note = f"\n\n📊 已生成{kind_zh}（前端可在 SSE meta 事件中接收）"

    return (
        f"**SQL:**\n```sql\n{result.sql}\n```\n\n"
        f"**思路:** {result.reasoning}\n\n"
        f"**结果（{result.row_count} 行）:**\n{report.markdown}"
        f"{chart_note}"
    )
