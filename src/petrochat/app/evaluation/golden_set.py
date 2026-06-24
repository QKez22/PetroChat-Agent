"""Golden Set evaluator.

The evaluator is intentionally offline-first. It reads private Golden Set files
from a local ignored directory, computes reproducible contract metrics, and can
optionally score prediction JSONL files produced by future agent runs.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from petrochat.app.sql import validate_sql

REQUIRED_FILES = {
    "turns": "golden_dialogue_turns.csv",
    "memory": "golden_memory_state.csv",
    "sql": "golden_sql_expectation.csv",
    "rag": "golden_rag_evidence.csv",
    "rubric": "golden_scoring_rubric.csv",
    "validation": "validation_summary.json",
}

WRITE_SQL_PATTERN = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE)\b", re.I)
SELECT_STAR_PATTERN = re.compile(r"SELECT\s+\*", re.I)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _loads_json(value: str, default: Any) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _required_path(golden_dir: Path, key: str) -> Path:
    path = golden_dir / REQUIRED_FILES[key]
    if not path.exists():
        raise FileNotFoundError(f"missing Golden Set file: {path}")
    return path


def _load_golden(golden_dir: Path) -> dict[str, Any]:
    return {
        "turns": _read_csv(_required_path(golden_dir, "turns")),
        "memory": _read_csv(_required_path(golden_dir, "memory")),
        "sql": _read_csv(_required_path(golden_dir, "sql")),
        "rag": _read_csv(_required_path(golden_dir, "rag")),
        "rubric": _read_csv(_required_path(golden_dir, "rubric")),
        "validation": _read_json(_required_path(golden_dir, "validation")),
    }


def _dataset_profile(data: dict[str, Any]) -> dict[str, Any]:
    turns = data["turns"]
    return {
        "dialogue_count": len({row["dialogue_id"] for row in turns}),
        "turn_count": len(turns),
        "sql_expectation_count": len(data["sql"]),
        "rag_evidence_count": len(data["rag"]),
        "memory_state_count": len(data["memory"]),
        "rubric_count": len(data["rubric"]),
        "scenario_counts": dict(Counter(row["scenario_type"] for row in turns)),
        "role_counts": dict(Counter(row["user_role"] for row in turns)),
        "difficulty_counts": dict(Counter(row["difficulty"] for row in turns)),
    }


def _memory_contract(data: dict[str, Any]) -> dict[str, Any]:
    memory_rows = data["memory"]
    use_counts = []
    ignore_counts = []
    after_key_counts = []
    clarification_count = 0
    for row in memory_rows:
        should_use = _loads_json(row.get("memory_should_use", ""), [])
        should_ignore = _loads_json(row.get("memory_should_ignore", ""), [])
        memory_after = _loads_json(row.get("memory_after", ""), {})
        use_counts.append(len(should_use))
        ignore_counts.append(len(should_ignore))
        after_key_counts.append(len(memory_after) if isinstance(memory_after, dict) else 0)
        if str(row.get("requires_clarification", "")).lower() == "true":
            clarification_count += 1

    total = len(memory_rows) or 1
    return {
        "turns": len(memory_rows),
        "requires_memory_use_turns": sum(1 for n in use_counts if n > 0),
        "requires_memory_ignore_turns": sum(1 for n in ignore_counts if n > 0),
        "requires_clarification_turns": clarification_count,
        "avg_use_keys": round(sum(use_counts) / total, 3),
        "avg_ignore_keys": round(sum(ignore_counts) / total, 3),
        "avg_memory_after_keys": round(sum(after_key_counts) / total, 3),
    }


def _sql_contract(data: dict[str, Any]) -> dict[str, Any]:
    rows = data["sql"]
    valid_count = 0
    select_star = 0
    write_ops = 0
    filter_counts = []
    table_counter: Counter[str] = Counter()
    invalid_examples: list[dict[str, str]] = []

    for row in rows:
        sql_template = row.get("expected_sql_template", "")
        result = validate_sql(sql_template)
        if result.ok:
            valid_count += 1
        elif len(invalid_examples) < 5:
            invalid_examples.append({
                "dialogue_id": row.get("dialogue_id", ""),
                "turn_id": row.get("turn_id", ""),
                "reason": result.reason,
            })
        if SELECT_STAR_PATTERN.search(sql_template):
            select_star += 1
        if WRITE_SQL_PATTERN.search(sql_template):
            write_ops += 1

        filters = _loads_json(row.get("expected_filters", ""), {})
        filter_counts.append(len(filters) if isinstance(filters, dict) else 0)
        for table in _loads_json(row.get("expected_tables", ""), []):
            table_counter[str(table)] += 1

    total = len(rows) or 1
    return {
        "template_count": len(rows),
        "template_valid_count": valid_count,
        "template_valid_rate": round(valid_count / total, 4),
        "select_star_violations": select_star,
        "write_operation_violations": write_ops,
        "avg_expected_filter_count": round(sum(filter_counts) / total, 3),
        "expected_table_counts": dict(table_counter),
        "invalid_examples": invalid_examples,
    }


def _rag_contract(data: dict[str, Any]) -> dict[str, Any]:
    rows = data["rag"]
    keyword_counts = []
    must_point_counts = []
    forbidden_counts = []
    source_counter: Counter[str] = Counter()

    for row in rows:
        keyword_counts.append(len(_loads_json(row.get("query_keywords", ""), [])))
        must_point_counts.append(len(_loads_json(row.get("must_include_points", ""), [])))
        forbidden_counts.append(len(_loads_json(row.get("forbidden_points", ""), [])))
        source_counter[row.get("expected_source_file", "")] += 1

    total = len(rows) or 1
    return {
        "evidence_count": len(rows),
        "avg_keywords": round(sum(keyword_counts) / total, 3),
        "avg_must_include_points": round(sum(must_point_counts) / total, 3),
        "avg_forbidden_points": round(sum(forbidden_counts) / total, 3),
        "source_file_counts": dict(source_counter.most_common(10)),
    }


def _rubric_profile(data: dict[str, Any]) -> dict[str, Any]:
    rows = data["rubric"]
    dimensions = [
        "memory_score",
        "retrieval_score",
        "sql_score",
        "answer_score",
        "permission_score",
        "total_score",
    ]
    summary: dict[str, Any] = {"rubric_count": len(rows)}
    for dim in dimensions:
        values = [int(row[dim]) for row in rows if row.get(dim, "").isdigit()]
        summary[f"avg_{dim}"] = round(sum(values) / len(values), 3) if values else 0
    return summary


def _prediction_metrics(data: dict[str, Any], prediction_path: Path | None) -> dict[str, Any] | None:
    if prediction_path is None:
        return None

    predictions = _read_jsonl(prediction_path)
    pred_by_key = {
        (str(row.get("dialogue_id")), str(row.get("turn_id"))): row
        for row in predictions
    }

    sql_rows = data["sql"]
    rag_rows = data["rag"]
    sql_present = 0
    sql_valid = 0
    sql_table_hits = 0
    sql_filter_hits = 0
    sql_filter_total = 0

    for row in sql_rows:
        pred = pred_by_key.get((row["dialogue_id"], row["turn_id"]))
        if not pred:
            continue
        sql = str(pred.get("sql") or "")
        if sql:
            sql_present += 1
            if validate_sql(sql).ok:
                sql_valid += 1
        expected_tables = [str(t).lower() for t in _loads_json(row.get("expected_tables", ""), [])]
        if sql and all(table in sql.lower() for table in expected_tables):
            sql_table_hits += 1
        filters = _loads_json(row.get("expected_filters", ""), {})
        if isinstance(filters, dict):
            for value in filters.values():
                if value is None:
                    continue
                sql_filter_total += 1
                if str(value).lower() in sql.lower():
                    sql_filter_hits += 1

    rag_hits = 0
    rag_scored = 0
    for row in rag_rows:
        pred = pred_by_key.get((row["dialogue_id"], row["turn_id"]))
        if not pred:
            continue
        retrieved = pred.get("retrieved") or []
        if not isinstance(retrieved, list):
            retrieved = []
        expected_source = row.get("expected_source_file", "")
        source_hit = any(expected_source and expected_source in str(item) for item in retrieved[:5])
        rag_scored += 1
        if source_hit:
            rag_hits += 1

    return {
        "prediction_count": len(predictions),
        "sql_present_rate": round(sql_present / (len(sql_rows) or 1), 4),
        "sql_validation_rate": round(sql_valid / (sql_present or 1), 4),
        "sql_table_recall": round(sql_table_hits / (len(sql_rows) or 1), 4),
        "sql_filter_value_recall": round(sql_filter_hits / (sql_filter_total or 1), 4),
        "rag_recall_at_5": round(rag_hits / (rag_scored or 1), 4),
        "rag_scored_count": rag_scored,
    }


def _write_outputs(result: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "golden_eval_summary.json"
    md_path = out_dir / "golden_eval_summary.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(result), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def _render_markdown(result: dict[str, Any]) -> str:
    profile = result["dataset_profile"]
    sql = result["sql_contract"]
    memory = result["memory_contract"]
    rag = result["rag_contract"]
    prediction = result.get("prediction_metrics")
    lines = [
        "# PetroChat-Agent Golden Set Evaluation",
        "",
        "## Dataset",
        "",
        f"- Dialogues: {profile['dialogue_count']}",
        f"- Turns: {profile['turn_count']}",
        f"- SQL expectations: {profile['sql_expectation_count']}",
        f"- RAG evidence rows: {profile['rag_evidence_count']}",
        "",
        "## Contract Metrics",
        "",
        f"- SQL template valid rate: {sql['template_valid_rate']}",
        f"- SQL select-star violations: {sql['select_star_violations']}",
        f"- SQL write-operation violations: {sql['write_operation_violations']}",
        f"- Memory turns requiring inherited keys: {memory['requires_memory_use_turns']}",
        f"- Memory turns requiring ignored keys: {memory['requires_memory_ignore_turns']}",
        f"- RAG avg keywords: {rag['avg_keywords']}",
        f"- RAG avg must-include points: {rag['avg_must_include_points']}",
    ]
    if prediction:
        lines.extend([
            "",
            "## Prediction Metrics",
            "",
            f"- Prediction count: {prediction['prediction_count']}",
            f"- SQL validation rate: {prediction['sql_validation_rate']}",
            f"- SQL table recall: {prediction['sql_table_recall']}",
            f"- SQL filter value recall: {prediction['sql_filter_value_recall']}",
            f"- RAG Recall@5: {prediction['rag_recall_at_5']}",
        ])
    else:
        lines.extend([
            "",
            "## Prediction Metrics",
            "",
            "- No prediction file provided. This run only profiles the Golden Set and validates contracts.",
        ])
    lines.append("")
    return "\n".join(lines)


def evaluate_golden_set(
    golden_dir: Path,
    out_dir: Path | None = None,
    prediction_path: Path | None = None,
) -> dict[str, Any]:
    data = _load_golden(golden_dir)
    result: dict[str, Any] = {
        "golden_dir": str(golden_dir),
        "dataset_profile": _dataset_profile(data),
        "memory_contract": _memory_contract(data),
        "sql_contract": _sql_contract(data),
        "rag_contract": _rag_contract(data),
        "rubric_profile": _rubric_profile(data),
        "declared_validation_summary": data["validation"],
    }
    prediction_metrics = _prediction_metrics(data, prediction_path)
    if prediction_metrics is not None:
        result["prediction_metrics"] = prediction_metrics
        result["prediction_path"] = str(prediction_path)
    if out_dir is not None:
        result["outputs"] = _write_outputs(result, out_dir)
    return result
