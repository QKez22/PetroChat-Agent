"""Report 模块离线测试 —— 不依赖 MySQL / LLM。"""

from __future__ import annotations

import pandas as pd

from petrochat.app.report import (
    df_to_markdown,
    pop_last_report,
    render_chart,
    render_report,
    suggest_chart_type,
)


# ============== df_to_markdown ==============

def test_empty_df() -> None:
    assert "0 行" in df_to_markdown(pd.DataFrame())


def test_basic_df_to_md() -> None:
    df = pd.DataFrame({"name": ["a", "b"], "count": [1, 2]})
    md = df_to_markdown(df)
    assert "| name | count |" in md
    assert "| a | 1 |" in md


def test_truncate_long_df() -> None:
    df = pd.DataFrame({"x": range(100)})
    md = df_to_markdown(df, max_rows=10)
    assert "后续 90 行省略" in md
    # 应该包含表头 + 分隔 + 10 行 = 12 行
    assert md.count("\n|") <= 12


def test_escape_pipes_and_newlines() -> None:
    df = pd.DataFrame({"x": ["a|b\nc"]})
    md = df_to_markdown(df)
    assert "|" in md
    # 单元格内的 | 应被转成 /
    assert "a/b" in md


# ============== suggest_chart_type ==============

def test_suggest_no_chart_for_empty() -> None:
    assert suggest_chart_type(pd.DataFrame()) == "none"


def test_suggest_pie_few_categories() -> None:
    df = pd.DataFrame({"category": ["A", "B", "C"], "value": [10, 20, 30]})
    assert suggest_chart_type(df) == "pie"


def test_suggest_bar_many_categories() -> None:
    df = pd.DataFrame({
        "dept": [f"D{i}" for i in range(15)],
        "count": list(range(15)),
    })
    assert suggest_chart_type(df) == "bar"


def test_suggest_line_for_time_series() -> None:
    df = pd.DataFrame({
        "report_time": pd.date_range("2026-01-01", periods=10),
        "count": list(range(10)),
    })
    assert suggest_chart_type(df) == "line"


def test_suggest_no_chart_when_no_numeric() -> None:
    df = pd.DataFrame({"a": ["x", "y"], "b": ["p", "q"]})
    assert suggest_chart_type(df) == "none"


# ============== render_chart ==============

def test_render_bar_returns_base64() -> None:
    df = pd.DataFrame({
        "dept": ["A", "B", "C"],
        "running": [10, 5, 3],
    })
    uri, kind = render_chart(df, kind="bar", title="测试")
    assert uri is not None
    assert uri.startswith("data:image/png;base64,")
    assert kind == "bar"


def test_render_pie_returns_base64() -> None:
    df = pd.DataFrame({
        "type": ["巡检", "维护", "会议"],
        "count": [50, 30, 20],
    })
    uri, kind = render_chart(df, kind="pie")
    assert uri is not None
    assert kind == "pie"


def test_render_chart_handles_empty() -> None:
    uri, kind = render_chart(pd.DataFrame(), kind="auto")
    assert uri is None
    assert kind == "none"


# ============== render_report (end-to-end) ==============

def test_render_report_full_pipeline() -> None:
    df = pd.DataFrame({"dept": ["A", "B"], "n": [10, 20]})
    rep = render_report(df, title="部门统计", with_chart=True)
    assert "| dept | n |" in rep.markdown
    assert rep.row_count == 2
    assert rep.columns == ["dept", "n"]
    assert rep.chart_kind in ("pie", "bar")
    assert rep.chart_data_uri is not None


def test_pop_last_report_clears_state() -> None:
    df = pd.DataFrame({"x": [1, 2]})
    render_report(df, with_chart=False)
    r1 = pop_last_report()
    r2 = pop_last_report()
    assert r1 is not None
    assert r2 is None  # pop 后清空
