from __future__ import annotations

import csv
import json
from pathlib import Path

from petrochat.app.evaluation import evaluate_golden_set


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_evaluate_golden_set_profiles_contracts(tmp_path: Path) -> None:
    golden = tmp_path / "golden"
    out_dir = tmp_path / "out"
    golden.mkdir()

    _write_csv(golden / "golden_dialogue_turns.csv", [
        {
            "dialogue_id": "d1",
            "turn_id": "1",
            "user_role": "engineer",
            "scenario_type": "nl2sql_condition_memory",
            "difficulty": "medium",
            "user_message": "查任务",
            "expected_intent": "sql",
            "expected_answer_points": "[]",
            "forbidden_behavior": "[]",
        }
    ])
    _write_csv(golden / "golden_memory_state.csv", [
        {
            "dialogue_id": "d1",
            "turn_id": "1",
            "memory_before": "{}",
            "memory_update": "{\"operation_department\":\"炼油一部\"}",
            "memory_after": "{\"operation_department\":\"炼油一部\"}",
            "memory_should_use": "[\"operation_department\"]",
            "memory_should_ignore": "[]",
            "requires_clarification": "False",
        }
    ])
    _write_csv(golden / "golden_sql_expectation.csv", [
        {
            "dialogue_id": "d1",
            "turn_id": "1",
            "expected_tables": "[\"affair_task\"]",
            "expected_join": "",
            "expected_fields": "[\"task_id\"]",
            "expected_filters": "{\"affair_task.operation_department\":\"炼油一部\"}",
            "expected_group_by": "",
            "expected_order_by": "",
            "expected_limit": "20",
            "expected_sql_template": "SELECT task_id FROM affair_task WHERE operation_department = '炼油一部' LIMIT 20;",
            "forbidden_sql_operations": "[]",
        }
    ])
    _write_csv(golden / "golden_rag_evidence.csv", [
        {
            "dialogue_id": "d1",
            "turn_id": "1",
            "expected_source_file": "制度.docx",
            "expected_section": "1",
            "expected_chunk_id": "chunk-1",
            "query_keywords": "[\"ITPM\"]",
            "must_include_points": "[\"说明依据\"]",
            "forbidden_points": "[]",
        }
    ])
    _write_csv(golden / "golden_scoring_rubric.csv", [
        {
            "dialogue_id": "d1",
            "turn_id": "1",
            "memory_score": "25",
            "retrieval_score": "20",
            "sql_score": "20",
            "answer_score": "20",
            "permission_score": "15",
            "total_score": "100",
            "critical_failures": "[]",
        }
    ])
    (golden / "validation_summary.json").write_text(
        json.dumps({"dialogue_count": 1, "turn_count": 1}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = evaluate_golden_set(golden_dir=golden, out_dir=out_dir)

    assert result["dataset_profile"]["dialogue_count"] == 1
    assert result["memory_contract"]["requires_memory_use_turns"] == 1
    assert result["sql_contract"]["template_valid_rate"] == 1
    assert result["rag_contract"]["evidence_count"] == 1
    assert result["quality_gate"]["status"] == "profile-only"
    assert result["quality_gate"]["checks"][0]["id"] == "sql_template_valid_rate"
    assert (out_dir / "golden_eval_summary.json").exists()
    assert (out_dir / "golden_eval_summary.md").exists()


def test_evaluate_golden_set_prediction_quality_metrics(tmp_path: Path) -> None:
    golden = tmp_path / "golden"
    golden.mkdir()

    _write_csv(golden / "golden_dialogue_turns.csv", [
        {
            "dialogue_id": "d1",
            "turn_id": "1",
            "user_role": "engineer",
            "scenario_type": "rag_sql_memory",
            "difficulty": "hard",
            "user_message": "query refinery-1 task and explain policy",
            "expected_intent": "qa",
            "expected_answer_points": "[\"safe operation\"]",
            "forbidden_behavior": "[]",
        }
    ])
    _write_csv(golden / "golden_memory_state.csv", [
        {
            "dialogue_id": "d1",
            "turn_id": "1",
            "memory_before": "{\"operation_department\":\"refinery-1\",\"old_department\":\"legacy\"}",
            "memory_update": "{}",
            "memory_after": "{\"operation_department\":\"refinery-1\"}",
            "memory_should_use": "[\"operation_department\"]",
            "memory_should_ignore": "[\"old_department\"]",
            "requires_clarification": "False",
        }
    ])
    _write_csv(golden / "golden_sql_expectation.csv", [
        {
            "dialogue_id": "d1",
            "turn_id": "1",
            "expected_tables": "[\"affair_task\"]",
            "expected_join": "",
            "expected_fields": "[\"task_id\"]",
            "expected_filters": "{\"affair_task.operation_department\":\"refinery-1\"}",
            "expected_group_by": "",
            "expected_order_by": "",
            "expected_limit": "20",
            "expected_sql_template": (
                "SELECT task_id FROM affair_task "
                "WHERE operation_department = 'refinery-1' LIMIT 20;"
            ),
            "forbidden_sql_operations": "[]",
        }
    ])
    _write_csv(golden / "golden_rag_evidence.csv", [
        {
            "dialogue_id": "d1",
            "turn_id": "1",
            "expected_source_file": "policy.docx",
            "expected_section": "2.1",
            "expected_chunk_id": "chunk-9",
            "query_keywords": "[\"policy\"]",
            "must_include_points": "[\"safe operation\"]",
            "forbidden_points": "[\"legacy\"]",
        }
    ])
    _write_csv(golden / "golden_scoring_rubric.csv", [
        {
            "dialogue_id": "d1",
            "turn_id": "1",
            "memory_score": "25",
            "retrieval_score": "20",
            "sql_score": "20",
            "answer_score": "20",
            "permission_score": "15",
            "total_score": "100",
            "critical_failures": "[]",
        }
    ])
    (golden / "validation_summary.json").write_text("{}", encoding="utf-8")

    prediction_path = tmp_path / "predictions.jsonl"
    prediction_path.write_text(
        json.dumps({
            "dialogue_id": "d1",
            "turn_id": "1",
            "status": "ok",
            "latency_ms": 120,
            "route": "qa",
            "question": "query task",
            "answer": "The answer covers safe operation.",
            "sql": "SELECT task_id FROM affair_task WHERE operation_department = 'refinery-1' LIMIT 20",
            "retrieved": [
                {"source_doc": "policy.docx", "section": "2.1", "chunk_id": "chunk-9"},
                {"source_doc": "other.docx", "section": "1"},
            ],
            "memory_used": ["101"],
            "execution_correct": True,
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    result = evaluate_golden_set(golden, prediction_path=prediction_path)
    metrics = result["prediction_metrics"]

    assert metrics["sql_contract_accuracy"] == 1
    assert metrics["sql_execution_accuracy"] == 1
    assert metrics["rag_recall_at_5"] == 1
    assert metrics["rag_mrr"] == 1
    assert metrics["rag_evidence_coverage"] == 1
    assert metrics["rag_faithfulness_proxy"] == 1
    assert metrics["memory_hit_rate"] == 1
    assert metrics["memory_ignore_violation_rate"] == 0
    assert result["quality_gate"]["status"] == "pass"
    assert result["quality_gate"]["failedCount"] == 0


def test_quality_gate_marks_prediction_regression(tmp_path: Path) -> None:
    golden = tmp_path / "golden"
    golden.mkdir()

    _write_csv(golden / "golden_dialogue_turns.csv", [
        {
            "dialogue_id": "d1",
            "turn_id": "1",
            "user_role": "engineer",
            "scenario_type": "rag_context_memory",
            "difficulty": "medium",
            "user_message": "explain policy",
            "expected_intent": "qa",
            "expected_answer_points": "[]",
            "forbidden_behavior": "[]",
        }
    ])
    _write_csv(golden / "golden_memory_state.csv", [
        {
            "dialogue_id": "d1",
            "turn_id": "1",
            "memory_before": "{}",
            "memory_update": "{}",
            "memory_after": "{}",
            "memory_should_use": "[\"operation_department\"]",
            "memory_should_ignore": "[\"old_department\"]",
            "requires_clarification": "False",
        }
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
            "dialogue_id": "d1",
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
            "dialogue_id": "d1",
            "turn_id": "1",
            "memory_score": "25",
            "retrieval_score": "20",
            "sql_score": "20",
            "answer_score": "20",
            "permission_score": "15",
            "total_score": "100",
            "critical_failures": "[]",
        }
    ])
    (golden / "validation_summary.json").write_text("{}", encoding="utf-8")

    prediction_path = tmp_path / "predictions.jsonl"
    prediction_path.write_text(
        json.dumps({
            "dialogue_id": "d1",
            "turn_id": "1",
            "status": "error",
            "latency_ms": 20000,
            "route": "qa",
            "answer": "",
            "sql": "DROP TABLE affair_task",
            "retrieved": [],
            "memory_used": [],
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    result = evaluate_golden_set(golden, prediction_path=prediction_path)
    gate = result["quality_gate"]
    statuses = {item["id"]: item["status"] for item in gate["checks"]}

    assert gate["status"] == "fail"
    assert statuses["success_rate"] == "fail"
    assert statuses["sql_validation_rate"] == "fail"
    assert statuses["rag_recall_at_5"] == "warn"
