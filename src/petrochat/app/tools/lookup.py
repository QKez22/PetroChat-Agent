"""精确查询工具：按文档+章节号查、在指定文档内做语义检索。

跟 retrieve_specs 互补：
  - retrieve_specs：跨文档语义检索（向量相似度），适合开放问题
  - lookup_section：精确按编号查（metadata where 过滤），适合"4.2.2 条款写了啥"
  - search_within_doc：在某份规范内语义检索，适合"高桥细则里关于备件的规定"
"""

from __future__ import annotations

from langchain_core.tools import tool

from ..rag import query as _vector_query


@tool
def lookup_section(source_doc_hint: str, section_number: str) -> str:
    """精确按章节号查询规范条款（不走向量检索，走元数据过滤）。

    适用场景：用户已知章节号，想要原文。比如"高桥石化备品配件管理细则的 1.4.1 写的什么"。

    Args:
        source_doc_hint: 文档名片段（部分匹配），如 "高桥石化" 或 "设备完整性"
        section_number:  完整章节号，如 "1.4.1" / "4.2.2"

    Returns:
        匹配到的条款全文（可能多条），找不到返回提示语。
    """
    # Chroma 的 where 过滤不支持 LIKE，只支持精确等值 / $in / $contains。
    # 做法：用 $eq section_number + 用 contains 查 source_doc，再 Python 端按 source_doc_hint 过滤
    where = {"section_number": {"$eq": section_number.strip()}}
    try:
        results = _vector_query(
            query_text=section_number,  # 用编号作 query 提升排序合理性，但主要靠 where 过滤
            top_k=20,
            where=where,
        )
    except Exception as e:
        return f"查询失败: {e}"

    if not results:
        return f"未找到章节号 '{section_number}'。"

    # 按 source_doc_hint 二次过滤
    hint = source_doc_hint.strip().lower()
    if hint:
        matched = [r for r in results if hint in r.metadata.get("source_doc", "").lower()]
        if not matched:
            # 没匹配到时，把所有命中条款的 source_doc 列出来提示
            sources = {r.metadata.get("source_doc", "?") for r in results}
            return (f"章节号 '{section_number}' 在以下文档中存在，但都不匹配 "
                    f"'{source_doc_hint}'：\n" + "\n".join(f"  - {s}" for s in sources))
        results = matched

    return "\n\n---\n\n".join(
        f"[出自 {r.metadata.get('source_doc', '?')} 第 {r.metadata.get('section_number', '?')} 条]\n"
        f"{r.content}"
        for r in results[:5]
    )


@tool
def search_within_doc(query: str, source_doc_hint: str, top_k: int = 5) -> str:
    """在指定规范文档内做语义检索（限定 source_doc 过滤）。

    适用：用户限定了规范范围，如 "在高桥石化备品配件管理细则里查关于储备目录的规定"。

    Args:
        query: 自然语言查询
        source_doc_hint: 文档名片段（部分匹配）
        top_k: 返回条数，默认 5

    Returns:
        命中的条款集合，含章节号与原文。
    """
    # Chroma 的 metadata 过滤不支持 LIKE，先全集合 query 再 Python 端过滤
    try:
        results = _vector_query(query_text=query, top_k=top_k * 4)
    except Exception as e:
        return f"检索失败: {e}"

    hint = source_doc_hint.strip().lower()
    matched = [r for r in results if hint in r.metadata.get("source_doc", "").lower()]
    if not matched:
        return f"在文档 '{source_doc_hint}' 中未找到与 '{query}' 相关的条款。"

    return "\n\n---\n\n".join(
        f"[出自 {r.metadata.get('source_doc', '?')} 第 {r.metadata.get('section_number', '?')} 条]\n"
        f"{r.content}"
        for r in matched[:top_k]
    )
