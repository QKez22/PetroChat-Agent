"""query_database 工具：让 ReAct agent 能直接查 MySQL 业务库。

为什么把 4 步压成一个 @tool：
  ReAct agent 不需要管 SQL 生成 / 校验 / 执行的内部步骤；
  它只关心"问问题 → 拿结果"。细粒度子图在 Step 4.5 用 Supervisor 模式重新拆开。
"""

from __future__ import annotations

from langchain_core.tools import tool

from ..sql import nl2sql


def _format_rows_markdown(columns: list[str], rows: list[dict], max_rows: int = 50) -> str:
    """把 SQL 结果渲染成 Markdown 表（截断超长）。"""
    if not rows:
        return "_(0 行)_"
    head = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = []
    for r in rows[:max_rows]:
        cells = []
        for c in columns:
            v = r.get(c)
            cells.append("" if v is None else str(v).replace("\n", " ").replace("|", "/"))
        body.append("| " + " | ".join(cells) + " |")
    if len(rows) > max_rows:
        body.append(f"| _… 后续 {len(rows) - max_rows} 行省略_ |" + " |" * (len(columns) - 1))
    return "\n".join([head, sep, *body])


@tool
def query_database(question: str) -> str:
    """查询事务任务管理 MySQL 数据库（affair 事务表 / affair_task 任务表）。

    适用场景：用户问题涉及具体业务数据查询，如：
      - 某专业 / 部门 / 设备的事务清单
      - 任务执行进度 / 上传统计
      - 即将到期的事务、需要开票的任务
      - 各部门数量、类型分布等统计

    Args:
        question: 用户的自然语言问题（中文）

    Returns:
        Markdown 字符串：含生成的 SQL、推理说明、结果表格；失败时含错误诊断。
    """
    result = nl2sql(question)

    if not result.ok:
        parts = [f"❌ 查询失败（阶段：{result.stage}）"]
        if result.sql:
            parts.append(f"**生成的 SQL:**\n```sql\n{result.sql}\n```")
        parts.append(f"**错误:** {result.error}")
        return "\n\n".join(parts)

    table_md = _format_rows_markdown(result.columns, result.rows)
    return (
        f"**SQL:**\n```sql\n{result.sql}\n```\n\n"
        f"**思路:** {result.reasoning}\n\n"
        f"**结果（{result.row_count} 行）:**\n{table_md}"
    )
