"""Report 层：DataFrame → Markdown 表 + base64 图表。

设计：
  报表对象同时携带 markdown（喂给 LLM / 前端展示）和 chart_data_uri（侧信道传 SSE meta）。
  base64 PNG 通过请求状态或工具 artifact 返回, 不送进 LLM 上下文。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

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
    title: str = ""

    def to_artifact(self) -> dict:
        return asdict(self)



def render_report(
    df: pd.DataFrame,
    title: str = "",
    with_chart: bool = True,
    max_rows: int = 50,
) -> Report:
    """生成本次调用独立持有的 Report。"""
    md = df_to_markdown(df, max_rows=max_rows)
    chart_uri, chart_kind = (None, "none")
    if with_chart and not df.empty:
        chart_uri, chart_kind = render_chart(df, kind="auto", title=title)
    return Report(
        markdown=md,
        chart_data_uri=chart_uri,
        chart_kind=chart_kind,
        row_count=len(df),
        columns=df.columns.tolist(),
        title=title,
    )


__all__ = [
    "Report",
    "render_report",
    "df_to_markdown",
    "render_chart",
    "suggest_chart_type",
]
