"""Prompt 模板集中管理。

把 prompt 跟节点代码分开，便于：
1. 改 prompt 不动业务代码
2. 后续做 prompt 版本管理 / A-B 测试
3. 面试时清晰展示"我们如何约束 LLM"
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

# ============================================================
# 问答节点：基于召回片段生成答案
# ============================================================
QA_SYSTEM_PROMPT = """你是中国石化炼化企业的设备完整性管理专家，专门解答石化行业标准规范类问题。

【回答规则】
1. **只基于下面提供的"参考资料"作答**，参考资料里没有的信息绝不编造。
2. 如果参考资料无法回答问题，直接回复"根据当前知识库，未找到相关条款的明确规定。"
3. 答案中**必须用方括号标注引用的章节号**，例如：[3.1.2]、[4.2.1]，便于用户回溯原文。
4. 答案要简洁专业，用术语而非口语；避免"我认为""我觉得"等主观表达。
5. 如有多个相关条款，按重要性整合表述，不要简单堆砌片段。
"""

QA_USER_PROMPT_TEMPLATE = """【参考资料】
{context}

【问题】
{question}

请基于上述参考资料作答。"""

QA_PROMPT = ChatPromptTemplate.from_messages([
    ("system", QA_SYSTEM_PROMPT),
    ("user", QA_USER_PROMPT_TEMPLATE),
])


def format_context(documents: list) -> str:
    """把检索到的 Document 列表格式化为给 LLM 的"参考资料"块。

    每个片段前置 [N.N.N 章节号]，让 LLM 容易在答案里引用。
    """
    if not documents:
        return "（没有找到相关参考资料）"
    parts = []
    for d in documents:
        sec = d.metadata.get("section_number", "?")
        parts.append(f"[{sec}] {d.page_content}")
    return "\n\n".join(parts)
