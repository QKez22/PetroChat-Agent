from __future__ import annotations

import csv
import json
from pathlib import Path

from langchain_core.messages import AIMessage

from petrochat.app.evaluation import evaluate_golden_set, generate_predictions


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _make_minimal_golden(tmp_path: Path) -> Path:
    golden = tmp_path / "golden"
    golden.mkdir()
    _write_csv(golden / "golden_dialogue_turns.csv", [
        {
            "dialogue_id": "d1",
            "turn_id": "1",
            "user_role": "engineer",
            "scenario_type": "nl2sql_condition_memory",
            "difficulty": "medium",
            "user_message": "查炼油一部任务",
            "expected_intent": "sql",
            "expected_answer_points": "[\"返回任务\"]",
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
            "memory_should_use": "[]",
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
    return golden


def test_oracle_replay_writes_predictions_and_evaluates(tmp_path: Path) -> None:
    golden = _make_minimal_golden(tmp_path)
    output = tmp_path / "predictions.jsonl"

    summary = generate_predictions(golden, output, mode="oracle")
    assert summary["prediction_count"] == 1
    assert output.exists()

    row = json.loads(output.read_text(encoding="utf-8").strip())
    assert row["mode"] == "oracle"
    assert "affair_task" in row["sql"]
    assert row["status"] == "ok"

    result = evaluate_golden_set(golden, out_dir=tmp_path / "out", prediction_path=output)
    assert result["prediction_metrics"]["prediction_count"] == 1
    assert result["prediction_metrics"]["success_rate"] == 1
    assert result["prediction_metrics"]["sql_validation_rate"] == 1
    assert result["prediction_metrics"]["sql_table_recall"] == 1


def test_agent_replay_uses_runner_and_writes_summary(tmp_path: Path) -> None:
    golden = _make_minimal_golden(tmp_path)
    output = tmp_path / "agent_predictions.jsonl"
    summary_path = tmp_path / "agent_predictions.summary.json"

    async def fake_runner(state: dict) -> dict:
        assert state["session_id"] == "eval-smoke-d1"
        assert state["user_id"] == "1"
        return {
            **state,
            "next": "sql",
            "messages": [
                *state["messages"],
                AIMessage(content="**SQL:**\n```sql\nSELECT task_id FROM affair_task LIMIT 20\n```"),
            ],
            "long_term_memories": [{"id": "101", "content": "默认炼油一部"}],
        }

    summary = generate_predictions(
        golden,
        output,
        mode="agent",
        limit=1,
        eval_user_id="1",
        run_id="smoke",
        summary_path=summary_path,
        runner=fake_runner,
    )

    row = json.loads(output.read_text(encoding="utf-8").strip())
    assert row["mode"] == "agent"
    assert row["run_id"] == "smoke"
    assert row["session_id"] == "eval-smoke-d1"
    assert row["eval_user_id"] == "1"
    assert row["route"] == "sql"
    assert row["memory_used"] == ["101"]
    assert "affair_task" in row["sql"]

    assert summary["prediction_summary"]["success_rate"] == 1
    assert summary["prediction_summary"]["error_count"] == 0
    saved_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert saved_summary["run_id"] == "smoke"
