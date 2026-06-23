"""DataFrame → Markdown 表（手写，不依赖 tabulate）。"""

from __future__ import annotations

import pandas as pd


def df_to_markdown(df: pd.DataFrame, max_rows: int = 50, max_col_chars: int = 80) -> str:
    """渲染 DataFrame 为 GitHub-flavor Markdown 表。

    Args:
        df: 数据
        max_rows: 超过则截断尾部并标注省略
        max_col_chars: 单元格字符上限，避免长 GROUP_CONCAT 撑爆排版
    """
    if df.empty:
        return "_(0 行)_"

    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |"]
    lines.append("| " + " | ".join(["---"] * len(cols)) + " |")

    for _, row in df.head(max_rows).iterrows():
        cells = []
        for c in df.columns:
            v = row[c]
            if pd.isna(v):
                cells.append("")
                continue
            s = str(v).replace("\n", " ").replace("|", "/")
            if len(s) > max_col_chars:
                s = s[: max_col_chars - 1] + "…"
            cells.append(s)
        lines.append("| " + " | ".join(cells) + " |")

    md = "\n".join(lines)
    if len(df) > max_rows:
        md += f"\n\n_… 后续 {len(df) - max_rows} 行省略，总共 {len(df)} 行_"
    return md
