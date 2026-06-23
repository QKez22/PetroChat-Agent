"""SQL 层：MySQL 引擎、schema、NL2SQL 全链路。"""

from .agent import Nl2SqlResult, nl2sql
from .engine import get_engine, healthcheck, list_tables
from .executor import ExecutionResult, execute_sql
from .generator import SqlPlan, clear_caches, generate_sql
from .schema import (
    dump_all_schemas,
    dump_table_schema,
    format_schemas_for_llm,
    format_table_schema_md,
)
from .validator import ValidationResult, validate_sql

__all__ = [
    "get_engine", "healthcheck", "list_tables",
    "dump_table_schema", "dump_all_schemas",
    "format_table_schema_md", "format_schemas_for_llm",
    "SqlPlan", "generate_sql", "clear_caches",
    "ValidationResult", "validate_sql",
    "ExecutionResult", "execute_sql",
    "Nl2SqlResult", "nl2sql",
]
