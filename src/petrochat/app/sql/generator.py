"""NL → SQL 生成器：DeepSeek 结构化输出。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from pydantic import BaseModel, Field

from ..core.config import get_settings
from ..core.llm import get_chat_llm
from .schema import dump_all_schemas, format_schemas_for_llm

PROJECT_ROOT = Path(__file__).resolve().parents[4]
EXAMPLES_FILE = PROJECT_ROOT / "data" / "sql_examples.yaml"


class SqlPlan(BaseModel):
    sql: str = Field(description="MySQL 8 兼容的 SELECT 语句，单条，不要分号结尾")
    reasoning: str = Field(description="一两句话说明：选了哪些表 / 关键字段 / 注意点（中文）")


@lru_cache(maxsize=1)
def _cached_schema_md() -> str:
    return format_schemas_for_llm(dump_all_schemas())


@lru_cache(maxsize=1)
def _cached_examples() -> tuple[list[dict], list[str]]:
    """YAML 结构 {examples: [...], domain_knowledge: [...]}。"""
    if not EXAMPLES_FILE.exists():
        return [], []
    raw = yaml.safe_load(EXAMPLES_FILE.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return [], []
    examples = [e for e in (raw.get("examples") or []) if isinstance(e, dict)]
    knowledge = list(raw.get("domain_knowledge") or [])
    return examples, knowledge


def get_domain_knowledge() -> str:
    """生成与验收共享项目维护的业务口径，避免两端对同一术语理解不同。"""
    return "\n".join(_cached_examples()[1])


def _build_system_prompt(schema_md: str | None = None, extra_rules: str = "") -> str:
    s = get_settings()
    schema_context = schema_md or _cached_schema_md()
    examples, knowledge = _cached_examples()

    examples_md = "\n\n".join(
        f"问：{e['question']}\nSQL:\n```sql\n{e['sql'].strip()}\n```"
        for e in examples
    )
    knowledge_md = "\n".join(f"- {k}" for k in knowledge)

    return f"""你是 MySQL 8 专家，把用户的中文问题转成 SELECT 语句。

【可用表 schema】
{schema_context}

【业务知识铁则（必读，违反会出错）】
{knowledge_md}

【参考样例】
{examples_md}

【硬性规则】
1. 只能产出单条 SELECT 语句，禁止 INSERT/UPDATE/DELETE/DDL；不要分号结尾。
2. 严格遵守上面的【业务知识铁则】，特别是反直觉字段和 varchar 时间字段的处理。
3. MySQL 8 方言，可以用 CTE / 窗口函数。
4. 默认会自动注入 LIMIT {s.sql_default_limit}，你不必显式写 LIMIT；除非用户问 Top-N。
5. 字段使用反引号或不加都行；最终 SQL 要可直接执行。
6. 如果用户消息包含【最近用户约束】或【SQL过滤提示】，这些是上游解析出的业务条件，必须优先继承并写入 WHERE/GROUP BY。
7. 聚合输出使用明确别名。设备数量按本体设备编码去重；关联查询统计事务/任务也必须按对应业务 ID 去重。
8. “各部门”不能直接按逗号拼接的 execution_department 分组；不清楚归属口径时不要擅自用部门组合代替。
{extra_rules}
"""


def _invoke_sql_plan(question: str, system_prompt: str, log_label: str) -> SqlPlan:
    llm = get_chat_llm().with_structured_output(SqlPlan, method="function_calling")
    logger.info("{} 入参: {}", log_label, question[:80])
    plan: SqlPlan = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=question),
    ])
    logger.info("{} 输出 SQL: {}", log_label, plan.sql[:120].replace("\n", " "))
    return plan


def generate_sql(question: str, schema_md: str | None = None) -> SqlPlan:
    """把自然语言问题转成 SqlPlan。

    method='function_calling'：DeepSeek 兼容层不支持 json_schema response_format，
    必须用 function_calling 模式（兼容 phase 2 的 bind_tools 机制）。
    """
    return _invoke_sql_plan(
        question=question,
        system_prompt=_build_system_prompt(schema_md=schema_md),
        log_label="generate_sql",
    )


def repair_sql(
    question: str,
    invalid_sql: str,
    validation_error: str,
    schema_md: str | None = None,
) -> SqlPlan:
    """Repair one generated SQL statement using validator feedback."""

    extra_rules = """
6. 你正在修复一条未通过校验的 SQL。必须优先消除校验错误，不要改变用户问题语义。
7. 不要解释错误，只返回修复后的单条 SELECT SQL 和简短 reasoning。
"""
    repair_question = f"""用户问题：
{question}

未通过校验的 SQL：
```sql
{invalid_sql}
```

校验错误：
{validation_error}
"""
    return _invoke_sql_plan(
        question=repair_question,
        system_prompt=_build_system_prompt(schema_md=schema_md, extra_rules=extra_rules),
        log_label="repair_sql",
    )


def clear_caches() -> None:
    """测试 / dev 期使用：清空 schema 与样例缓存。"""
    _cached_schema_md.cache_clear()
    _cached_examples.cache_clear()
    from .schema_narrowing import clear_schema_narrowing_cache

    clear_schema_narrowing_cache()
    from .contract import contract_schemas

    contract_schemas.cache_clear()


def preview_schema_md() -> str:
    """给 CLI / 调试用的 schema 预览（清缓存后重抓一次）。"""
    clear_caches()
    return _cached_schema_md()
