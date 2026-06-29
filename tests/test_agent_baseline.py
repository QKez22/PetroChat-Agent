from __future__ import annotations

import csv
import json
from pathlib import Path

from langchain_core.messages import AIMessage

from petrochat.app.evaluation.baseline import (
    build_baseline_plan,
    parse_scenario_targets,
    run_agent_baseline,
)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _make_baseline_golden(tmp_path: Path) -> Path:
    golden = tmp_path / "golden"
    golden.mkdir()
    turns = [
        {
            "dialogue_id": "d1",
            "turn_id": "1",
            "user_role": "engineer",
            "scenario_type": "nl2sql_condition_memory",
            "difficulty": "medium",
            "user_message": "query private task one",
            "expected_intent": "sql",
            "expected_answer_points": "[]",
            "forbidden_behavior": "[]",
        },
        {
            "dialogue_id": "d1",
            "turn_id": "2",
            "user_role": "engineer",
            "scenario_type": "nl2sql_condition_memory",
            "difficulty": "medium",
            "user_message": "query private task two",
            "expected_intent": "sql",
            "expected_answer_points": "[]",
            "forbidden_behavior": "[]",
        },
        {
            "dialogue_id": "d2",
            "turn_id": "1",
            "user_role": "engineer",
            "scenario_type": "rag_context_memory",
            "difficulty": "hard",
            "user_message": "private rag question",
            "expected_intent": "qa",
            "expected_answer_points": "[\"safe operation\"]",
            "forbidden_behavior": "[]",
        },
        {
            "dialogue_id": "d3",
            "turn_id": "1",
            "user_role": "admin",
            "scenario_type": "system_permission_memory",
            "difficulty": "easy",
            "user_message": "private permission question",
            "expected_intent": "general",
            "expected_answer_points": "[]",
            "forbidden_behavior": "[]",
        },
    ]
    _write_csv(golden / "golden_dialogue_turns.csv", turns)
    _write_csv(golden / "golden_memory_state.csv", [
        {
            "dialogue_id": row["dialogue_id"],
            "turn_id": row["turn_id"],
            "memory_before": "{}",
            "memory_update": "{}",
            "memory_after": "{}",
            "memory_should_use": "[]",
            "memory_should_ignore": "[]",
            "requires_clarification": "False",
        }
        for row in turns
    ])
    _write_csv(golden / "golden_sql_expectation.csv", [
        {
            "dialogue_id": "d1",
            "turn_id": "1",
            "expected_tables": "[\"affair_task\"]",
            "expected_join": "",
            "expected_fields": "[\"task_id\"]",
            "expected_filters": "{}",
            "expected_group_by": "",
            "expected_order_by": "",
            "expected_limit": "20",
            "expected_sql_template": "SELECT task_id FROM affair_task LIMIT 20;",
            "forbidden_sql_operations": "[]",
        }
    ])
    _write_csv(golden / "golden_rag_evidence.csv", [
        {
            "dialogue_id": "d2",
            "turn_id": "1",
            "expected_source_file": "policy.docx",
            "expected_section": "2.1",
            "expected_chunk_id": "chunk-9",
            "query_keywords": "[\"policy\"]",
            "must_include_points": "[\"safe operation\"]",
            "forbidden_points": "[]",
        }
    ])
    _write_csv(golden / "golden_scoring_rubric.csv", [
        {
            "dialogue_id": row["dialogue_id"],
            "turn_id": row["turn_id"],
            "memory_score": "25",
            "retrieval_score": "20",
            "sql_score": "20",
            "answer_score": "20",
            "permission_score": "15",
            "total_score": "100",
            "critical_failures": "[]",
        }
        for row in turns
    ])
    (golden / "validation_summary.json").write_text("{}", encoding="utf-8")
    return golden


def test_parse_scenario_targets() -> None:
    assert parse_scenario_targets(["rag_context_memory=2"]) == {"rag_context_memory": 2}


def test_baseline_plan_is_sanitized(tmp_path: Path) -> None:
    golden = _make_baseline_golden(tmp_path)

    plan = build_baseline_plan(
        golden,
        scenario_targets={"nl2sql_condition_memory": 1, "rag_context_memory": 1},
        max_turns=3,
    )

    assert plan["selectedDialogueIds"] == ["d1", "d2"]
    assert plan["selectedDialogueCount"] == 2
    assert plan["selectedTurnCount"] == 3
    assert plan["effectiveTurnLimit"] == 3
    assert "private" not in json.dumps(plan, ensure_ascii=False)


def test_run_agent_baseline_plan_only_writes_report(tmp_path: Path) -> None:
    golden = _make_baseline_golden(tmp_path)
    out_dir = tmp_path / "out"

    result = run_agent_baseline(
        golden,
        out_dir,
        scenario_targets={"nl2sql_condition_memory": 1},
        execute_agent=False,
    )

    assert result["execute_agent"] is False
    assert result["replay_summary"] is None
    assert Path(result["outputs"]["plan"]).exists()
    assert Path(result["outputs"]["report"]).exists()
    assert not (out_dir / "agent_baseline_predictions.jsonl").exists()


def test_run_agent_baseline_executes_with_fake_runner(tmp_path: Path) -> None:
    golden = _make_baseline_golden(tmp_path)
    out_dir = tmp_path / "out"

    async def fake_runner(state: dict) -> dict:
        return {
            **state,
            "next": "sql",
            "messages": [
                *state["messages"],
                AIMessage(content="ok\n```sql\nSELECT task_id FROM affair_task LIMIT 20\n```"),
            ],
            "retrieved": [
                {
                    "chunk_id": "chunk-9",
                    "score": 0.1,
                    "metadata": {"source_doc": "policy.docx", "section_number": "2.1"},
                }
            ],
            "long_term_memories": [{"id": "m1"}],
        }

    result = run_agent_baseline(
        golden,
        out_dir,
        scenario_targets={"nl2sql_condition_memory": 1, "rag_context_memory": 1},
        max_turns=2,
        eval_user_id="1",
        run_id="baseline-test",
        execute_agent=True,
        runner=fake_runner,
    )

    assert result["replay_summary"]["prediction_count"] == 2
    assert result["evaluation_summary"]["prediction_metrics"]["prediction_count"] == 2
    assert Path(result["outputs"]["summary"]).exists()
    assert (out_dir / "agent_baseline_predictions.jsonl").exists()
    report = Path(result["outputs"]["report"]).read_text(encoding="utf-8")
    assert "Quality gate" in report
    assert "private" not in report
