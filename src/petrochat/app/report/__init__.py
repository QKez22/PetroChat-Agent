"""Report 层：DataFrame → Markdown 表 + base64 图表。

设计：
  报表对象同时携带 markdown（喂给 LLM / 前端展示）和 chart_data_uri（侧信道传 SSE meta）。
  base64 PNG 不送进 LLM 上下文（30KB+，浪费 token），通过 pop_last_report 拿出来。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .chart import render_chart, suggest_chart_type
from .formatter import df_to_markdown


@dataclass
class Report:
    markdown: str
    chart_data_uri: str | None
    chart_kind: str
    row_count: int
    columns: list[str]


# 模块级"最后一次报表"——侧信道
_LAST_REPORT: Report | None = None


def render_report(
    df: pd.DataFrame,
    title: str = "",
    with_chart: bool = True,
    max_rows: int = 50,
) -> Report:
    """从 DataFrame 生成 Report，并存入侧信道。"""
    global _LAST_REPORT
    md = df_to_markdown(df, max_rows=max_rows)
    chart_uri, chart_kind = (None, "none")
    if with_chart and not df.empty:
        chart_uri, chart_kind = render_chart(df, kind="auto", title=title)
    rep = Report(
        markdown=md,
        chart_data_uri=chart_uri,
        chart_kind=chart_kind,
        row_count=len(df),
        columns=df.columns.tolist(),
    )
    _LAST_REPORT = rep
    return rep


def pop_last_report() -> Report | None:
    """取出并清空最近一次的报表（侧信道）。

    SSE 层在 query_database 工具结束后调用，把 chart 通过 meta 事件推给前端。
    """
    global _LAST_REPORT
    r = _LAST_REPORT
    _LAST_REPORT = None
    return r


def peek_last_report() -> Report | None:
    """只看不取（测试用）。"""
    return _LAST_REPORT


__all__ = [
    "Report",
    "render_report",
    "pop_last_report",
    "peek_last_report",
    "df_to_markdown",
    "render_chart",
    "suggest_chart_type",
]
