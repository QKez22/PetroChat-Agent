"""原始需求丢失、SQL 能执行但语义错误的反例回归。"""

from __future__ import annotations

import importlib

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from petrochat.app.agent.requirements import extract_requirements, plan_coverage
from petrochat.app.agent.tasks import TaskSpec
from petrochat.app.core.config import get_settings
from petrochat.app.sql import agent, contract
from petrochat.app.sql.executor import ExecutionResult
from petrochat.app.sql.generator import SqlPlan

QUESTION = "解释 ITPM，再统计各部门采用 ITPM 策略的设备数量"
SQL_QUESTION = "统计各部门设备数量"
GOOD = "SELECT t.operation_department AS dept, COUNT(DISTINCT t.body_equipment_code) AS n FROM affair_task t GROUP BY t.operation_department"


@pytest.fixture
def schemas(monkeypatch):
    def schema(table, names):
        return {
            "table_name": table,
            "columns": [
                {
                    "COLUMN_NAME": n,
                    "COLUMN_COMMENT": "",
                    "COLUMN_TYPE": "varchar",
                    "COLUMN_KEY": "",
                    "IS_NULLABLE": "YES",
                }
                for n in names
            ],
        }

    data = [
        schema(
            "affair_task",
            [
                "task_id",
                "associated_affair_id",
                "body_equipment_code",
                "operation_department",
                "maintenance_type",
                "specialty",
            ],
        ),
        schema("affair", ["affair_id", "execution_department", "specialty", "affair_name"]),
    ]
    monkeypatch.setattr(contract, "contract_schemas", lambda: data)
    monkeypatch.setenv("MYSQL_TABLES_WHITELIST", "affair,affair_task")
    monkeypatch.setenv("SQL_PIPELINE_MODE", "legacy")
    monkeypatch.setenv("SQL_REPAIR_MAX_ATTEMPTS", "1")
    get_settings.cache_clear()
    return data


def test_source_requirements_capture_group_and_filter():
    requirements = extract_requirements(QUESTION)
    assert [r["worker"] for r in requirements] == ["qa", "sql"]
    sql = requirements[1]
    assert QUESTION[sql["start"] : sql["end"]] == sql["source"]
    assert sql["contract"]["groups"] == ["部门"]
    assert sql["contract"]["strategy"] == "ITPM"
    assert sql["contract"]["entity"] == "设备"


@pytest.mark.parametrize(
    "sql",
    [
        None,
        "统计采用 ITPM 策略的设备数量",
        "统计各部门设备数量",
        "统计各部门采用 ITPM 策略的事务数量",
    ],
)
def test_incomplete_plan_rejected(sql):
    tasks = [TaskSpec(worker="qa", instruction="解释 ITPM")]
    if sql:
        tasks.append(TaskSpec(worker="sql", instruction=sql))
    assert plan_coverage(extract_requirements(QUESTION), tasks)[0]


def test_continuation_filter_is_not_dropped():
    reqs = extract_requirements("统计设备数量，只看炼油一部")
    assert reqs[0]["contract"]["filters"]["departments"] == ["炼油一部"]
    assert plan_coverage(reqs, [TaskSpec(worker="sql", instruction="统计设备数量")])[0]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(DISTINCT body_equipment_code) n FROM affair_task",
        "SELECT operation_department, COUNT(*) n FROM affair_task GROUP BY operation_department",
        "SELECT execution_department, COUNT(DISTINCT affair_id) n FROM affair GROUP BY execution_department",
        "SELECT t.operation_department, COUNT(t.body_equipment_code) n FROM affair_task t JOIN affair a ON a.affair_id=t.associated_affair_id GROUP BY t.operation_department",
        "SELECT '部门' dept, COUNT(DISTINCT body_equipment_code) n FROM affair_task",
    ],
)
def test_successful_but_wrong_sql_rejected(schemas, sql):
    assert contract.validate_contract(sql, contract.extract_contract(SQL_QUESTION))


def test_grouped_distinct_device_count_passes_rules(schemas):
    assert not contract.validate_contract(GOOD, contract.extract_contract(SQL_QUESTION))


def test_group_and_order_output_aliases_are_resolved(schemas):
    sql = GOOD.replace("GROUP BY t.operation_department", "GROUP BY dept ORDER BY n DESC")
    assert not contract.validate_contract(sql, contract.extract_contract(SQL_QUESTION))


@pytest.mark.parametrize(
    "predicate", ["1=1 OR t.specialty='仪'", "NOT t.specialty='仪'", "t.specialty='电'"]
)
def test_filter_literal_presence_is_not_proof(schemas, predicate):
    sql = GOOD.replace(" GROUP BY", f" WHERE {predicate} GROUP BY")
    assert contract.validate_contract(sql, contract.extract_contract("统计各部门仪表设备数量"))


def test_unknown_strategy_mapping_fails_closed(schemas, monkeypatch):
    monkeypatch.setenv("SQL_STRATEGY_FIELD", "")
    get_settings.cache_clear()
    errors = contract.validate_contract(GOOD, contract.extract_contract(QUESTION))
    assert any("策略" in e for e in errors)


def test_configured_strategy_requires_correct_predicate(schemas, monkeypatch):
    monkeypatch.setenv("SQL_STRATEGY_FIELD", "affair_task.maintenance_type")
    monkeypatch.setenv("SQL_STRATEGY_VALUES", '{"ITPM":"itpm_code"}')
    get_settings.cache_clear()
    req = contract.extract_contract(QUESTION)
    assert contract.validate_contract(GOOD, req)
    sql = GOOD.replace(" GROUP BY", " WHERE t.maintenance_type='itpm_code' GROUP BY")
    assert not contract.validate_contract(sql, req)


@pytest.mark.parametrize("mode", ["legacy", "optimized"])
def test_missing_group_repaired_before_database_execution(schemas, monkeypatch, mode):
    from petrochat.app.sql.schema_narrowing import SchemaSelection

    monkeypatch.setenv("SQL_PIPELINE_MODE", mode)
    get_settings.cache_clear()
    monkeypatch.setattr(
        agent,
        "select_relevant_schema",
        lambda q: SchemaSelection(
            tables=["affair_task"],
            schema_md="test",
            total_table_count=1,
            reason="test",
            selected_column_count=6,
            total_column_count=6,
        ),
    )
    calls = []
    monkeypatch.setattr(
        agent,
        "generate_sql",
        lambda *a, **kw: SqlPlan(sql="SELECT COUNT(*) FROM affair_task", reasoning="bad"),
    )

    def repair(**kwargs):
        assert "分组" in kwargs["validation_error"]
        return SqlPlan(sql=GOOD, reasoning="fixed")

    monkeypatch.setattr(agent, "repair_sql", repair)
    monkeypatch.setattr(agent, "review_semantics", lambda *args: [])

    def execute(sql):
        calls.append(sql)
        return ExecutionResult(
            ok=True,
            sql_executed=sql,
            columns=["dept", "n"],
            rows=[{"dept": "A", "n": 2}],
            row_count=1,
        )

    monkeypatch.setattr(agent, "execute_sql", execute)
    result = agent.nl2sql(SQL_QUESTION)
    assert result.ok and result.execution_ok and result.semantic_status == "passed"
    assert result.repair_succeeded and len(calls) == 1
    assert "GROUP BY" in calls[0]


def test_failed_semantic_repair_never_executes(schemas, monkeypatch):
    bad = SqlPlan(sql="SELECT COUNT(*) FROM affair_task", reasoning="bad")
    monkeypatch.setattr(agent, "generate_sql", lambda *a, **kw: bad)
    repairs = []
    monkeypatch.setattr(agent, "repair_sql", lambda **kw: repairs.append(kw) or bad)
    monkeypatch.setattr(agent, "execute_sql", lambda sql: pytest.fail("未验收 SQL 不应执行"))
    result = agent.nl2sql(SQL_QUESTION)
    assert not result.ok and result.semantic_status == "failed"
    assert len(repairs) == 1


def test_result_truncation_and_wrong_columns_rejected():
    req = contract.extract_contract(SQL_QUESTION)
    assert contract.validate_result(GOOD + " LIMIT 2", req, ["dept", "n"], 2)
    assert contract.validate_result(GOOD, req, ["n"], 1)
    assert not contract.validate_result(GOOD, req, ["dept", "n"], 0)


def test_independent_sql_review_checks_original_request(schemas, monkeypatch):
    captured = []

    class Reviewer:
        def with_structured_output(self, *args, **kwargs):
            return self

        def invoke(self, messages):
            captured.extend(messages)
            return contract.SemanticReview(passed=False, issues=["遗漏未完成筛选"])

    monkeypatch.setattr(contract, "get_chat_llm", Reviewer)
    assert contract.review_semantics("统计未完成任务数量", "SELECT COUNT(*) FROM affair_task") == [
        "遗漏未完成筛选"
    ]
    assert any(isinstance(m, HumanMessage) and "未完成" in m.content for m in captured)


def test_plan_repair_is_bounded_and_records_sources(monkeypatch):
    module = importlib.import_module("petrochat.app.agent.nodes.supervisor_node")
    attempts = []

    class Planner:
        def with_structured_output(self, *args, **kwargs):
            return self

        def invoke(self, messages):
            attempts.append(messages)
            specs = [{"worker": "qa", "instruction": "解释 ITPM"}]
            if len(attempts) == 2:
                specs.append({"worker": "sql", "instruction": "统计各部门采用 ITPM 策略的设备数量"})
            return module.RouteDecision(next="qa", reasoning="test", tasks=specs)

    monkeypatch.setattr(module, "get_chat_llm", Planner)
    monkeypatch.setattr(module, "review_plan", lambda *args: [])
    output = module.supervisor_node({"question": QUESTION, "messages": [HumanMessage(QUESTION)]})
    assert len(attempts) == 2 and len(output["tasks"]) == 2
    assert output["tasks"][1]["requirements"][0]["contract"]["groups"] == ["部门"]


def test_execution_repair_cannot_bypass_semantic_gate(schemas, monkeypatch):
    from petrochat.app.sql.schema_narrowing import SchemaSelection

    monkeypatch.setenv("SQL_PIPELINE_MODE", "optimized")
    get_settings.cache_clear()
    monkeypatch.setattr(
        agent,
        "select_relevant_schema",
        lambda q: SchemaSelection(
            tables=["affair_task"],
            schema_md="test",
            total_table_count=1,
            reason="test",
            selected_column_count=6,
            total_column_count=6,
        ),
    )
    monkeypatch.setattr(agent, "generate_sql", lambda *a, **kw: SqlPlan(sql=GOOD, reasoning="good"))
    monkeypatch.setattr(agent, "review_semantics", lambda *args: [])
    monkeypatch.setattr(
        agent,
        "repair_sql",
        lambda **kw: SqlPlan(sql="SELECT COUNT(*) FROM affair_task", reasoning="bad repair"),
    )
    calls = []
    monkeypatch.setattr(
        agent,
        "execute_sql",
        lambda sql: calls.append(sql) or ExecutionResult(ok=False, error="temporary failure"),
    )
    result = agent.nl2sql(SQL_QUESTION)
    assert not result.ok and result.semantic_status == "failed"
    assert len(calls) == 1


def test_sql_reviewer_rejection_cannot_be_overridden_by_execution(schemas, monkeypatch):
    monkeypatch.setattr(agent, "generate_sql", lambda *a, **kw: SqlPlan(sql=GOOD, reasoning="good"))
    monkeypatch.setattr(agent, "repair_sql", lambda **kw: SqlPlan(sql=GOOD, reasoning="unchanged"))
    monkeypatch.setattr(agent, "review_semantics", lambda *args: ["无法确认设备范围"])
    monkeypatch.setattr(agent, "execute_sql", lambda sql: pytest.fail("审核失败不应执行"))
    result = agent.nl2sql(SQL_QUESTION)
    assert not result.ok and "设备范围" in result.error


def test_plan_review_is_independent_and_fail_closed(monkeypatch):
    module = importlib.import_module("petrochat.app.agent.requirements")
    captured = []

    class Reviewer:
        def with_structured_output(self, *args, **kwargs):
            return self

        def invoke(self, messages):
            captured.extend(messages)
            return contract.SemanticReview(passed=False, issues=["遗漏统计意图"])

    monkeypatch.setattr(module, "get_chat_llm", Reviewer)
    errors = module.review_plan(QUESTION, [TaskSpec(worker="qa", instruction="解释 ITPM")])
    assert errors == ["遗漏统计意图"]
    assert QUESTION in captured[-1].content


def test_plan_failure_stops_after_one_repair(monkeypatch):
    module = importlib.import_module("petrochat.app.agent.nodes.supervisor_node")
    calls = []

    class Planner:
        def with_structured_output(self, *args, **kwargs):
            return self

        def invoke(self, messages):
            calls.append(messages)
            return module.RouteDecision(next="FINISH", reasoning="遗漏统计", tasks=[])

    monkeypatch.setattr(module, "get_chat_llm", Planner)
    with pytest.raises(ValueError, match="计划覆盖校验"):
        module.supervisor_node({"question": QUESTION, "messages": [HumanMessage(QUESTION)]})
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_graph_does_not_mark_semantically_failed_sql_completed(schemas, monkeypatch):
    from petrochat.app.agent import build_initial_state
    from petrochat.app.agent.result import build_turn_result
    from petrochat.app.agent.runtime import run_graph

    graph = importlib.import_module("petrochat.app.agent.graph")
    supervisor = importlib.import_module("petrochat.app.agent.nodes.supervisor_node")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")

    class Planner:
        def with_structured_output(self, *args, **kwargs):
            return self

        def invoke(self, messages):
            return supervisor.RouteDecision(
                next="qa",
                reasoning="两项任务",
                tasks=[
                    {"worker": "qa", "instruction": "解释 ITPM"},
                    {"worker": "sql", "instruction": "统计各专业事务数量"},
                ],
            )

    monkeypatch.setattr(supervisor, "get_chat_llm", Planner)
    monkeypatch.setattr(supervisor, "review_plan", lambda *args: [])
    monkeypatch.setattr(
        graph,
        "qa_node",
        lambda state: {
            "messages": [AIMessage(content="ITPM 解释 [1.2]")],
            "retrieved": [{"content": "依据"}],
        },
    )
    bad = SqlPlan(sql="SELECT COUNT(*) FROM affair", reasoning="漏专业分组")
    monkeypatch.setattr(agent, "generate_sql", lambda *a, **kw: bad)
    monkeypatch.setattr(agent, "repair_sql", lambda **kw: bad)
    monkeypatch.setattr(agent, "execute_sql", lambda sql: pytest.fail("错误统计不能执行"))
    graph.build_graph.cache_clear()
    result = build_turn_result(
        await run_graph(graph.build_graph(), build_initial_state("解释 ITPM，并统计各专业事务数量"))
    )
    assert result.status == "partial" and not result.artifacts
    assert [t["status"] for t in result.tasks] == ["completed", "failed"]
    assert "分组" in result.answer and "ITPM 解释" in result.answer
