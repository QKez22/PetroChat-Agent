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

DEFAULT_QUALITY_GATE_THRESHOLDS = {
    "success_rate": 0.95,
    "sql_template_valid_rate": 0.95,
    "sql_validation_rate": 0.95,
    "sql_contract_accuracy": 0.85,
    "rag_recall_at_5": 0.85,
    "rag_mrr": 0.65,
    "rag_faithfulness_proxy": 0.85,
    "memory_hit_rate": 0.80,
    "memory_ignore_violation_rate": 0.0,
    "max_avg_latency_ms": 15000.0,
}


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


def _normalise_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _contains_text(haystack: str, needle: Any) -> bool:
    text = _normalise_text(needle)
    return bool(text) and text in haystack


def _json_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value or "")


def _prediction_text(prediction: dict[str, Any]) -> str:
    parts = [
        prediction.get("question"),
        prediction.get("answer"),
        prediction.get("sql"),
        prediction.get("memory_used"),
    ]
    return _normalise_text(" ".join(_json_text(part) for part in parts))


def _memory_values_for_key(row: dict[str, str], key: str) -> list[str]:
    values: list[str] = []
    for field in ("memory_before", "memory_update", "memory_after"):
        payload = _loads_json(row.get(field, ""), {})
        if isinstance(payload, dict) and key in payload:
            values.append(str(payload[key]))
    return values


def _memory_hit(row: dict[str, str], prediction: dict[str, Any], required_keys: list[str]) -> bool:
    memory_used = prediction.get("memory_used") or []
    if isinstance(memory_used, list) and memory_used:
        return True
    text = _prediction_text(prediction)
    for key in required_keys:
        if _contains_text(text, key):
            return True
        if any(_contains_text(text, value) for value in _memory_values_for_key(row, key)):
            return True
    return False


def _memory_ignore_violation(row: dict[str, str], prediction: dict[str, Any], ignored_key: str) -> bool:
    text = _prediction_text(prediction)
    if _contains_text(text, ignored_key):
        return True
    return any(_contains_text(text, value) for value in _memory_values_for_key(row, ignored_key))


def _retrieved_item_text(item: Any) -> str:
    if isinstance(item, dict):
        fields: list[Any] = [
            item.get("source_doc"),
            item.get("source"),
            item.get("section"),
            item.get("section_number"),
            item.get("chunk_id"),
            item.get("id"),
            item.get("content"),
            item.get("page_content"),
        ]
        metadata = item.get("metadata")
        if isinstance(metadata, dict):
            fields.extend([
                metadata.get("source_doc"),
                metadata.get("source"),
                metadata.get("section"),
                metadata.get("section_number"),
                metadata.get("chunk_id"),
                metadata.get("id"),
            ])
        return _normalise_text(" ".join(_json_text(field) for field in fields))
    return _normalise_text(item)


def _rag_item_matches(row: dict[str, str], item: Any) -> bool:
    text = _retrieved_item_text(item)
    expected_chunk = row.get("expected_chunk_id", "")
    expected_source = row.get("expected_source_file", "")
    expected_section = row.get("expected_section", "")
    if expected_chunk and _contains_text(text, expected_chunk):
        return True
    if expected_source and _contains_text(text, expected_source):
        if not expected_section or _contains_text(text, expected_section):
            return True
        return True
    return False


def _first_rag_rank(row: dict[str, str], retrieved: Any) -> int | None:
    rows = retrieved if isinstance(retrieved, list) else []
    for index, item in enumerate(rows, start=1):
        if _rag_item_matches(row, item):
            return index
    return None


def _must_point_coverage(row: dict[str, str], prediction: dict[str, Any]) -> tuple[int, int]:
    points = [str(item) for item in _loads_json(row.get("must_include_points", ""), [])]
    if not points:
        return 0, 0
    answer = _normalise_text(prediction.get("answer", ""))
    hits = sum(1 for point in points if _contains_text(answer, point))
    return hits, len(points)


def _has_forbidden_point(row: dict[str, str], prediction: dict[str, Any]) -> bool:
    points = [str(item) for item in _loads_json(row.get("forbidden_points", ""), [])]
    answer = _normalise_text(prediction.get("answer", ""))
    return any(_contains_text(answer, point) for point in points)


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "ok", "pass", "passed"}


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
    ok_count = sum(1 for row in predictions if row.get("status") == "ok")
    error_count = len(predictions) - ok_count
    latencies = [int(row.get("latency_ms") or 0) for row in predictions]
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
    sql_contract_hits = 0
    sql_execution_scored = 0
    sql_execution_correct = 0

    for row in sql_rows:
        pred = pred_by_key.get((row["dialogue_id"], row["turn_id"]))
        if not pred:
            continue
        sql = str(pred.get("sql") or "")
        sql_is_valid = False
        if sql:
            sql_present += 1
            sql_is_valid = validate_sql(sql).ok
            if sql_is_valid:
                sql_valid += 1
        expected_tables = [str(t).lower() for t in _loads_json(row.get("expected_tables", ""), [])]
        table_hit = bool(sql) and all(table in sql.lower() for table in expected_tables)
        if table_hit:
            sql_table_hits += 1
        filters = _loads_json(row.get("expected_filters", ""), {})
        row_filter_total = 0
        row_filter_hits = 0
        if isinstance(filters, dict):
            for value in filters.values():
                if value is None:
                    continue
                sql_filter_total += 1
                row_filter_total += 1
                if str(value).lower() in sql.lower():
                    sql_filter_hits += 1
                    row_filter_hits += 1
        row_filter_hit = row_filter_hits == row_filter_total
        if sql_is_valid and table_hit and row_filter_hit:
            sql_contract_hits += 1

        execution_correct = _optional_bool(pred.get("execution_correct"))
        if execution_correct is None:
            execution_correct = _optional_bool(pred.get("result_match"))
        if execution_correct is None:
            execution_correct = _optional_bool(pred.get("execution_ok"))
        if execution_correct is not None:
            sql_execution_scored += 1
            if execution_correct:
                sql_execution_correct += 1

    rag_hits = 0
    rag_scored = 0
    rag_reciprocal_rank_sum = 0.0
    rag_must_hits = 0
    rag_must_total = 0
    rag_faithful_hits = 0
    for row in rag_rows:
        pred = pred_by_key.get((row["dialogue_id"], row["turn_id"]))
        if not pred:
            continue
        retrieved = pred.get("retrieved") or []
        if not isinstance(retrieved, list):
            retrieved = []
        rank = _first_rag_rank(row, retrieved)
        must_hits, must_total = _must_point_coverage(row, pred)
        rag_must_hits += must_hits
        rag_must_total += must_total
        rag_scored += 1
        if rank is not None:
            rag_reciprocal_rank_sum += 1 / rank
        if rank is not None and rank <= 5:
            rag_hits += 1
        if rank is not None and not _has_forbidden_point(row, pred) and str(pred.get("answer") or "").strip():
            rag_faithful_hits += 1

    memory_rows = data["memory"]
    memory_required = 0
    memory_hits = 0
    memory_ignore_total = 0
    memory_ignore_violations = 0
    for row in memory_rows:
        pred = pred_by_key.get((row["dialogue_id"], row["turn_id"]))
        if not pred:
            continue
        should_use = [str(item) for item in _loads_json(row.get("memory_should_use", ""), [])]
        if should_use:
            memory_required += 1
            if _memory_hit(row, pred, should_use):
                memory_hits += 1
        should_ignore = [str(item) for item in _loads_json(row.get("memory_should_ignore", ""), [])]
        for ignored_key in should_ignore:
            memory_ignore_total += 1
            if _memory_ignore_violation(row, pred, ignored_key):
                memory_ignore_violations += 1

    return {
        "prediction_count": len(predictions),
        "ok_count": ok_count,
        "error_count": error_count,
        "success_rate": round(ok_count / (len(predictions) or 1), 4),
        "avg_latency_ms": round(sum(latencies) / (len(latencies) or 1), 2),
        "max_latency_ms": max(latencies) if latencies else 0,
        "sql_present_rate": round(sql_present / (len(sql_rows) or 1), 4),
        "sql_validation_rate": round(sql_valid / (sql_present or 1), 4),
        "sql_table_recall": round(sql_table_hits / (len(sql_rows) or 1), 4),
        "sql_filter_value_recall": round(sql_filter_hits / (sql_filter_total or 1), 4),
        "sql_contract_accuracy": round(sql_contract_hits / (len(sql_rows) or 1), 4),
        "sql_execution_accuracy": (
            round(sql_execution_correct / sql_execution_scored, 4)
            if sql_execution_scored
            else None
        ),
        "sql_execution_scored_count": sql_execution_scored,
        "rag_recall_at_5": round(rag_hits / (rag_scored or 1), 4),
        "rag_mrr": round(rag_reciprocal_rank_sum / (rag_scored or 1), 4),
        "rag_evidence_coverage": round(rag_must_hits / (rag_must_total or 1), 4),
        "rag_faithfulness_proxy": round(rag_faithful_hits / (rag_scored or 1), 4),
        "rag_scored_count": rag_scored,
        "memory_hit_rate": round(memory_hits / (memory_required or 1), 4),
        "memory_required_count": memory_required,
        "memory_ignore_violation_rate": round(
            memory_ignore_violations / (memory_ignore_total or 1), 4
        ),
        "memory_ignore_checked_count": memory_ignore_total,
    }


def _thresholds(overrides: dict[str, float] | None = None) -> dict[str, float]:
    values = dict(DEFAULT_QUALITY_GATE_THRESHOLDS)
    if overrides:
        values.update({key: float(value) for key, value in overrides.items()})
    return values


def _gate_check(
    check_id: str,
    label: str,
    value: float | int | None,
    target: float | int,
    operator: str,
    severity: str,
    detail: str = "",
) -> dict[str, Any]:
    if value is None:
        status = "skip"
        passed = None
    elif operator == ">=":
        passed = float(value) >= float(target)
        status = "pass" if passed else severity
    elif operator == "<=":
        passed = float(value) <= float(target)
        status = "pass" if passed else severity
    elif operator == "==":
        passed = value == target
        status = "pass" if passed else severity
    else:
        raise ValueError(f"unsupported gate operator: {operator}")

    return {
        "id": check_id,
        "label": label,
        "value": value,
        "target": target,
        "operator": operator,
        "status": status,
        "severity": severity,
        "passed": passed,
        "detail": detail,
    }


def _gate_label(status: str) -> str:
    labels = {
        "pass": "通过",
        "warn": "预警",
        "fail": "失败",
        "profile-only": "仅画像",
    }
    return labels.get(status, status)


def build_quality_gate(
    result: dict[str, Any],
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Build a compact quality gate for dashboards and CI checks."""

    gate_thresholds = _thresholds(thresholds)
    sql = result.get("sql_contract") or {}
    prediction = result.get("prediction_metrics") or {}
    checks = [
        _gate_check(
            "sql_template_valid_rate",
            "SQL 模板通过率",
            sql.get("template_valid_rate"),
            gate_thresholds["sql_template_valid_rate"],
            ">=",
            "fail",
            "Golden Set 中的期望 SQL 模板必须通过 AST 校验。",
        ),
        _gate_check(
            "write_operation_violations",
            "写操作违规数",
            sql.get("write_operation_violations"),
            0,
            "==",
            "fail",
            "NL2SQL 只允许只读 SELECT，不允许写操作。",
        ),
        _gate_check(
            "select_star_violations",
            "SELECT * 违规数",
            sql.get("select_star_violations"),
            0,
            "==",
            "warn",
            "演示和生产查询都应尽量显式选择字段。",
        ),
    ]

    if prediction:
        checks.extend([
            _gate_check(
                "success_rate",
                "Agent 成功率",
                prediction.get("success_rate"),
                gate_thresholds["success_rate"],
                ">=",
                "fail",
                "真实回放中 Agent 调用不能出现大量异常。",
            ),
            _gate_check(
                "sql_validation_rate",
                "SQL 校验率",
                prediction.get("sql_validation_rate"),
                gate_thresholds["sql_validation_rate"],
                ">=",
                "fail",
                "生成 SQL 必须稳定通过只读安全校验。",
            ),
            _gate_check(
                "sql_contract_accuracy",
                "SQL 合约准确率",
                prediction.get("sql_contract_accuracy"),
                gate_thresholds["sql_contract_accuracy"],
                ">=",
                "warn",
                "同时检查 SQL 合法性、期望表和过滤条件命中。",
            ),
            _gate_check(
                "rag_recall_at_5",
                "RAG Recall@5",
                prediction.get("rag_recall_at_5"),
                gate_thresholds["rag_recall_at_5"],
                ">=",
                "warn",
                "标注证据应出现在前 5 条检索结果内。",
            ),
            _gate_check(
                "rag_mrr",
                "RAG MRR",
                prediction.get("rag_mrr"),
                gate_thresholds["rag_mrr"],
                ">=",
                "warn",
                "越早命中证据，说明检索排序越可靠。",
            ),
            _gate_check(
                "rag_faithfulness_proxy",
                "忠实性代理指标",
                prediction.get("rag_faithfulness_proxy"),
                gate_thresholds["rag_faithfulness_proxy"],
                ">=",
                "warn",
                "基于检索命中、非空回答和 forbidden points 的规则代理指标。",
            ),
            _gate_check(
                "memory_hit_rate",
                "Memory Hit Rate",
                prediction.get("memory_hit_rate"),
                gate_thresholds["memory_hit_rate"],
                ">=",
                "warn",
                "需要继承记忆的轮次应召回或使用正确记忆。",
            ),
            _gate_check(
                "memory_ignore_violation_rate",
                "记忆忽略违规率",
                prediction.get("memory_ignore_violation_rate"),
                gate_thresholds["memory_ignore_violation_rate"],
                "<=",
                "fail",
                "应忽略的旧条件不能继续污染回答或 SQL。",
            ),
            _gate_check(
                "avg_latency_ms",
                "平均延迟",
                prediction.get("avg_latency_ms"),
                gate_thresholds["max_avg_latency_ms"],
                "<=",
                "warn",
                "用于发现工具调用、数据库查询或模型响应明显变慢。",
            ),
        ])

    statuses = [item["status"] for item in checks if item["status"] != "skip"]
    if not prediction:
        status = "profile-only"
    elif "fail" in statuses:
        status = "fail"
    elif "warn" in statuses:
        status = "warn"
    else:
        status = "pass"

    failed_checks = [item for item in checks if item["status"] in {"fail", "warn"}]
    return {
        "status": status,
        "label": _gate_label(status),
        "summary": (
            "仅完成 Golden Set 合约画像，尚未提供 prediction JSONL。"
            if status == "profile-only"
            else f"{len(failed_checks)} 项检查需要关注。"
            if failed_checks
            else "所有核心质量门禁均已通过。"
        ),
        "checks": checks,
        "failedCount": len([item for item in failed_checks if item["status"] == "fail"]),
        "warningCount": len([item for item in failed_checks if item["status"] == "warn"]),
        "thresholds": gate_thresholds,
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
    gate = result.get("quality_gate") or build_quality_gate(result)
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
        "",
        "## Quality Gate",
        "",
        f"- Status: {gate['status']} ({gate['label']})",
        f"- Summary: {gate['summary']}",
        f"- Failed checks: {gate['failedCount']}",
        f"- Warning checks: {gate['warningCount']}",
    ]
    if prediction:
        lines.extend([
            "",
            "## Prediction Metrics",
            "",
            f"- Prediction count: {prediction['prediction_count']}",
            f"- Agent success rate: {prediction.get('success_rate', 0)}",
            f"- Agent error count: {prediction.get('error_count', 0)}",
            f"- Avg latency ms: {prediction.get('avg_latency_ms', 0)}",
            f"- SQL validation rate: {prediction['sql_validation_rate']}",
            f"- SQL table recall: {prediction['sql_table_recall']}",
            f"- SQL filter value recall: {prediction['sql_filter_value_recall']}",
            f"- SQL contract accuracy: {prediction.get('sql_contract_accuracy', 0)}",
            f"- SQL execution accuracy: {prediction.get('sql_execution_accuracy')}",
            f"- RAG Recall@5: {prediction['rag_recall_at_5']}",
            f"- RAG MRR: {prediction.get('rag_mrr', 0)}",
            f"- RAG evidence coverage: {prediction.get('rag_evidence_coverage', 0)}",
            f"- RAG faithfulness proxy: {prediction.get('rag_faithfulness_proxy', 0)}",
            f"- Memory hit rate: {prediction.get('memory_hit_rate', 0)}",
            f"- Memory ignore violation rate: {prediction.get('memory_ignore_violation_rate', 0)}",
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
        result["quality_gate"] = build_quality_gate(result)
        result["outputs"] = _write_outputs(result, out_dir)
    else:
        result["quality_gate"] = build_quality_gate(result)
    return result
