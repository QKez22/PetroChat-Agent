"""NL → SQL 生成器：DeepSeek 结构化输出。

设计：
  - schema markdown 用 lru_cache 锁住，避免每次问都打 information_schema
  - few-shot 样例和"业务知识铁则"从 data/sql_examples.yaml 读
  - 用 Pydantic 结构化输出：sql + reasoning，便于审计 / 排错
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger
from pydantic import BaseModel, Field

from ..core.config import get_settings
from ..core.llm import get_chat_llm
from .schema import dump_all_schemas, format_schemas_for_llm

PROJECT_ROOT = Path(__file__).resolve().parents[4]
EXAMPLES_FILE = PROJECT_ROOT / "data" / "sql_examples.yaml"


class SqlPlan(BaseModel):
    """LLM 的结构化输出。"""

    sql: str = Field(description="MySQL 8 兼容的 SELECT 语句，单条，不要分号结尾")
    reasoning: str = Field(
        description="一两句话说明：选了哪些表 / 关键字段 / 注意点（用中文）",
    )


@lru_cache(maxsize=1)
def _cached_schema_md() -> str:
    """schema 在进程生命周期内只查一次。"""
    return format_schemas_for_llm(dump_all_schemas())


@lru_cache(maxsize=1)
def _cached_examples() -> tuple[list[dict], list[str]]:
    """(few-shot 样例, 业务知识铁则)。"""
    if not EXAMPLES_FILE.exists():
        return [], []
    raw = yaml.safe_load(EXAMPLES_FILE.read_text(encoding="utf-8"))
    examples: list[dict] = []
    knowledge: list[str] = []
    for item in raw or []:
        if isinstance(item, dict):
            if "question" in item and "sql" in item:
                examples.append(item)
            elif "_domain_knowledge" in item:
                knowledge = item["_domain_knowledge"] or []
    return examples, knowledge


def _build_system_prompt() -> str:
    s = get_settings()
    schema_md = _cached_schema_md()
    examples, knowledge = _cached_examples()

    examples_md = "\n\n".join(
        f"问：{e['question']}\nSQL:\n```sql\n{e['sql'].strip()}\n```"
        for e in examples
    )
    knowledge_md = "\n".join(f"- {k}" for k in knowledge)

    return f"""你是 MySQL 8 专家，把用户的中文问题转成 SELECT 语句。

【可用表 schema】
{schema_md}

【业务知识铁则（必读，违反会出错）】
{knowledge_md}

【参考样例】
{examples_md}

【硬性规则】
1. 只能产出单条 SELECT 语句，禁止 INSERT/UPDATE/DELETE/DDL；不要分号结尾。
2. 严格遵守上面的"业务知识铁则"，特别是反直觉字段（trigger_status 含义、ticket_flag 0=是）和 varchar 时间字段的处理。
3. MySQL 8 方言，可以用 CTE / 窗口函数。
4. 默认会自动注入 LIMIT {s.sql_default_limit}，你不必显式写 LIMIT；除非用户问 Top-N 之类需要小 LIMIT。
5. 字段使用反引号或不加都行；最终 SQL 要可直接执行。
"""


def generate_sql(question: str) -> SqlPlan:
    """把自然语言问题转成 SqlPlan（sql + reasoning）。"""
    llm = get_chat_llm().with_structured_output(SqlPlan)
    sys_prompt = _build_system_prompt()
    logger.info("generate_sql 入参: {}", question[:80])
    plan: SqlPlan = llm.invoke([
        SystemMessage(content=sys_prompt),
        HumanMessage(content=question),
    ])
    logger.info("generate_sql 输出 SQL: {}", plan.sql[:120].replace("\n", " "))
    return plan


def clear_caches() -> None:
    """测试 / dev 期使用：清空 schema 与样例缓存。"""
    _cached_schema_md.cache_clear()
    _cached_examples.cache_clear()
