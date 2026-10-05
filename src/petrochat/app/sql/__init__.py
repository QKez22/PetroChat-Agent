"""SQL 层：MySQL 引擎、schema、NL2SQL 全链路。"""

from .agent import Nl2SqlResult, nl2sql
from .engine import get_engine, healthcheck, list_tables
from .executor import ExecutionResult, execute_sql
from .generator import SqlPlan, clear_caches, generate_sql, repair_sql
from .hints import SqlBusinessHints, build_sql_question_with_hints, extract_sql_business_hints
from .schema import (
    dump_all_schemas,
    dump_table_schema,
    format_schemas_for_llm,
    format_table_schema_md,
)
from .schema_narrowing import SchemaSelection, clear_schema_narrowing_cache, select_relevant_schema
from .validator import ValidationResult, validate_sql

__all__ = [
    "get_engine", "healthcheck", "list_tables",
    "dump_table_schema", "dump_all_schemas",
    "format_table_schema_md", "format_schemas_for_llm",
    "SqlPlan", "generate_sql", "repair_sql", "clear_caches",
    "SqlBusinessHints", "build_sql_question_with_hints", "extract_sql_business_hints",
    "SchemaSelection", "select_relevant_schema", "clear_schema_narrowing_cache",
    "ValidationResult", "validate_sql",
    "ExecutionResult", "execute_sql",
    "Nl2SqlResult", "nl2sql",
]
