"""图表渲染：根据 DataFrame 形状自动选 bar / line / pie，输出 base64 PNG。

设计：
- matplotlib Agg 后端（无显示器服务器友好）
- 中文字体兜底链：Windows / macOS / Linux 常见字体
- 用 try/finally 确保 figure 关闭，避免内存泄漏
- 失败不抛异常，返回 None；上层不强依赖图表
"""

from __future__ import annotations

import base64
import io
from typing import Literal

import matplotlib

matplotlib.use("Agg")  # 必须在 import pyplot 之前

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from loguru import logger  # noqa: E402

# 中文字体兜底（顺序很重要：Windows 优先 YaHei，macOS 用 Arial Unicode）
matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "PingFang SC", "Arial Unicode MS",
    "Noto Sans CJK SC", "WenQuanYi Micro Hei", "DejaVu Sans",
]
matplotlib.rcParams["axes.unicode_minus"] = False

ChartKind = Literal["auto", "bar", "line", "pie", "none"]


def suggest_chart_type(df: pd.DataFrame) -> str:
    """根据 DataFrame 形状推荐图表类型。"""
    if df.empty or len(df) < 2:
        return "none"

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    non_numeric = [c for c in df.columns if c not in numeric_cols]

    if not numeric_cols:
        return "none"

    # 检测时间序列：列名含 time/date/时间/日期
    if non_numeric:
        time_col = next(
            (c for c in non_numeric
             if any(kw in c.lower() for kw in ("time", "date"))
             or any(kw in c for kw in ("时间", "日期"))),
            None,
        )
        if time_col and len(df) >= 3:
            return "line"

    # 单数值列 + 行数 ≤ 8：饼图
    if len(non_numeric) >= 1 and len(numeric_cols) == 1 and 2 <= len(df) <= 8:
        return "pie"

    # 1 类别列 + 1+ 数值列：柱状
    if len(non_numeric) >= 1 and len(df) <= 30:
        return "bar"

    return "none"


def render_chart(
    df: pd.DataFrame,
    kind: ChartKind = "auto",
    title: str = "",
) -> tuple[str | None, str]:
    """渲染图表。

    Returns:
        (data_uri, actual_kind)：data_uri 为 None 表示未渲染（数据不适合或失败）
    """
    actual_kind = suggest_chart_type(df) if kind == "auto" else kind
    if actual_kind == "none":
        return None, "none"

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    non_numeric = [c for c in df.columns if c not in numeric_cols]
    if not numeric_cols or not non_numeric:
        return None, "none"

    label_col = non_numeric[0]

    fig, ax = plt.subplots(figsize=(10, 5), dpi=80)
    try:
        if actual_kind == "bar":
            df_plot = df.set_index(label_col)
            df_plot[numeric_cols].plot(kind="bar", ax=ax)
            ax.set_xlabel(label_col)
            plt.xticks(rotation=30, ha="right")
        elif actual_kind == "line":
            df_plot = df.set_index(label_col)
            df_plot[numeric_cols].plot(kind="line", ax=ax, marker="o")
            ax.set_xlabel(label_col)
            plt.xticks(rotation=30, ha="right")
        elif actual_kind == "pie":
            df.set_index(label_col)[numeric_cols[0]].plot(
                kind="pie", ax=ax, autopct="%1.1f%%", startangle=90,
            )
            ax.set_ylabel("")
        else:
            return None, "none"

        if title:
            ax.set_title(title)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight")
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode("ascii")
        return f"data:image/png;base64,{b64}", actual_kind
    except Exception as e:
        logger.warning("图表渲染失败（已跳过）: {}", e)
        return None, "none"
    finally:
        plt.close(fig)
