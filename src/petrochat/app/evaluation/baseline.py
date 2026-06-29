"""Agent baseline replay planning and sanitized reporting."""

from __future__ import annotations

import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .golden_set import evaluate_golden_set
from .replay import AgentRunner, generate_predictions

DEFAULT_BASELINE_SCENARIO_TARGETS = {
    "nl2sql_condition_memory": 4,
    "rag_sql_hybrid_judgement": 3,
    "rag_context_memory": 3,
    "report_generation_memory": 2,
    "system_permission_memory": 2,
    "memory_control_edge_case": 2,
}


def parse_scenario_targets(values: list[str] | None) -> dict[str, int]:
    if not values:
        return dict(DEFAULT_BASELINE_SCENARIO_TARGETS)

    targets: dict[str, int] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"scenario target must use name=count format: {value}")
        name, count_text = value.split("=", 1)
        name = name.strip()
        if not name:
            raise ValueError(f"scenario name is empty: {value}")
        try:
            count = int(count_text)
        except ValueError as exc:
            raise ValueError(f"scenario count must be an integer: {value}") from exc
        if count <= 0:
            raise ValueError(f"scenario count must be positive: {value}")
        targets[name] = count
    return targets


def _read_turns(golden_dir: Path) -> list[dict[str, str]]:
    path = golden_dir / "golden_dialogue_turns.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing Golden Set turns file: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _dialogue_sort_key(dialogue_id: str) -> tuple[int, str]:
    digits = "".join(char for char in dialogue_id if char.isdigit())
    return (int(digits) if digits else 0, dialogue_id)


def build_baseline_plan(
    golden_dir: Path,
    scenario_targets: dict[str, int] | None = None,
    *,
    max_turns: int = 20,
) -> dict[str, Any]:
    """Select a deterministic, non-random baseline slice from private Golden Set."""

    targets = scenario_targets or DEFAULT_BASELINE_SCENARIO_TARGETS
    turns = _read_turns(golden_dir)
    by_dialogue: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in turns:
        by_dialogue[str(row.get("dialogue_id", ""))].append(row)

    for rows in by_dialogue.values():
        rows.sort(key=lambda item: int(item.get("turn_id") or 0))

    scenario_to_dialogues: dict[str, list[str]] = defaultdict(list)
    dialogue_profiles: dict[str, dict[str, Any]] = {}
    for dialogue_id, rows in sorted(by_dialogue.items(), key=lambda item: _dialogue_sort_key(item[0])):
        first = rows[0]
        scenario = str(first.get("scenario_type") or "unknown")
        scenario_to_dialogues[scenario].append(dialogue_id)
        dialogue_profiles[dialogue_id] = {
            "dialogue_id": dialogue_id,
            "scenario_type": scenario,
            "turn_count": len(rows),
            "user_role": first.get("user_role") or "",
            "difficulty": first.get("difficulty") or "",
        }

    selected_ids: list[str] = []
    skipped: dict[str, dict[str, int]] = {}
    for scenario, requested in targets.items():
        candidates = scenario_to_dialogues.get(scenario, [])
        selected = candidates[:requested]
        selected_ids.extend(selected)
        if len(selected) < requested:
            skipped[scenario] = {
                "requested": requested,
                "available": len(candidates),
                "selected": len(selected),
            }

    selected_ids = sorted(set(selected_ids), key=_dialogue_sort_key)
    selected_profiles = [dialogue_profiles[item] for item in selected_ids]
    selected_turn_count = sum(int(item["turn_count"]) for item in selected_profiles)
    scenario_counts = Counter(str(item["scenario_type"]) for item in selected_profiles)
    role_counts = Counter(str(item["user_role"]) for item in selected_profiles)
    difficulty_counts = Counter(str(item["difficulty"]) for item in selected_profiles)

    return {
        "golden_dir": str(golden_dir),
        "scenarioTargets": dict(targets),
        "maxTurns": max_turns,
        "selectedDialogueIds": selected_ids,
        "selectedDialogueCount": len(selected_ids),
        "selectedTurnCount": selected_turn_count,
        "effectiveTurnLimit": min(max_turns, selected_turn_count),
        "scenarioCounts": dict(scenario_counts),
        "roleCounts": dict(role_counts),
        "difficultyCounts": dict(difficulty_counts),
        "skippedScenarios": skipped,
        "privacyNote": (
            "Plan only contains IDs and aggregate metadata; raw questions, SQL and retrieval "
            "snippets remain in ignored local Golden Set files."
        ),
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def render_baseline_report(
    plan: dict[str, Any],
    replay_summary: dict[str, Any] | None = None,
    evaluation_summary: dict[str, Any] | None = None,
) -> str:
    prediction = (evaluation_summary or {}).get("prediction_metrics") or {}
    gate = (evaluation_summary or {}).get("quality_gate") or {}
    replay = (replay_summary or {}).get("prediction_summary") or {}

    lines = [
        "# Phase 10.2 Agent Baseline Replay",
        "",
        "## Plan",
        "",
        f"- Dialogues selected: {plan['selectedDialogueCount']}",
        f"- Turns in selected dialogues: {plan['selectedTurnCount']}",
        f"- Effective turn limit: {plan['effectiveTurnLimit']}",
        f"- Scenario counts: {json.dumps(plan['scenarioCounts'], ensure_ascii=False, sort_keys=True)}",
        f"- Role counts: {json.dumps(plan['roleCounts'], ensure_ascii=False, sort_keys=True)}",
        f"- Difficulty counts: {json.dumps(plan['difficultyCounts'], ensure_ascii=False, sort_keys=True)}",
        "",
        "## Replay",
        "",
    ]

    if replay_summary:
        lines.extend([
            f"- Run id: {replay_summary.get('run_id', '')}",
            f"- Mode: {replay_summary.get('mode', '')}",
            f"- Predictions: {replay_summary.get('prediction_count', 0)}",
            f"- Success rate: {replay.get('success_rate', 0)}",
            f"- Avg latency ms: {replay.get('avg_latency_ms', 0)}",
            f"- Route counts: {json.dumps(replay.get('route_counts', {}), ensure_ascii=False, sort_keys=True)}",
        ])
    else:
        lines.append("- Plan-only run. Add `--execute-agent` to call the real LangGraph agent.")

    lines.extend([
        "",
        "## Quality",
        "",
    ])
    if evaluation_summary:
        lines.extend([
            f"- Quality gate: {gate.get('status', '')} ({gate.get('label', '')})",
            f"- Gate summary: {gate.get('summary', '')}",
            f"- Agent success rate: {prediction.get('success_rate')}",
            f"- SQL contract accuracy: {prediction.get('sql_contract_accuracy')}",
            f"- RAG Recall@5: {prediction.get('rag_recall_at_5')}",
            f"- RAG MRR: {prediction.get('rag_mrr')}",
            f"- Memory Hit Rate: {prediction.get('memory_hit_rate')}",
        ])
    else:
        lines.append("- No evaluation metrics generated yet.")

    lines.extend([
        "",
        "## Privacy Boundary",
        "",
        "- This report intentionally excludes raw questions, full SQL and full retrieval snippets.",
        "- Full prediction JSONL stays under ignored `data/eval_results/` for local debugging only.",
        "",
    ])
    return "\n".join(lines)


def write_baseline_artifacts(
    out_dir: Path,
    plan: dict[str, Any],
    replay_summary: dict[str, Any] | None = None,
    evaluation_summary: dict[str, Any] | None = None,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / "agent_baseline_plan.json"
    report_path = out_dir / "agent_baseline_report.md"
    _write_json(plan_path, plan)
    report_path.write_text(
        render_baseline_report(plan, replay_summary, evaluation_summary),
        encoding="utf-8",
    )
    outputs = {
        "plan": str(plan_path),
        "report": str(report_path),
    }
    if replay_summary:
        summary_path = out_dir / "agent_baseline_summary.json"
        _write_json(summary_path, replay_summary)
        outputs["summary"] = str(summary_path)
    return outputs


def run_agent_baseline(
    golden_dir: Path,
    out_dir: Path,
    *,
    scenario_targets: dict[str, int] | None = None,
    max_turns: int = 20,
    eval_user_id: str = "0",
    run_id: str | None = None,
    execute_agent: bool = False,
    runner: AgentRunner | None = None,
) -> dict[str, Any]:
    plan = build_baseline_plan(
        golden_dir,
        scenario_targets=scenario_targets,
        max_turns=max_turns,
    )
    run_id = run_id or f"agent-baseline-{int(time.time())}"
    replay_summary: dict[str, Any] | None = None
    evaluation_summary: dict[str, Any] | None = None

    if execute_agent:
        predictions_path = out_dir / "agent_baseline_predictions.jsonl"
        replay_summary = generate_predictions(
            golden_dir=golden_dir,
            output_path=predictions_path,
            mode="agent",
            limit=max_turns,
            dialogue_ids=set(plan["selectedDialogueIds"]),
            eval_user_id=eval_user_id,
            run_id=run_id,
            summary_path=out_dir / "agent_baseline_replay_summary.json",
            runner=runner,
        )
        evaluation_summary = evaluate_golden_set(
            golden_dir=golden_dir,
            out_dir=out_dir,
            prediction_path=predictions_path,
        )

    outputs = write_baseline_artifacts(out_dir, plan, replay_summary, evaluation_summary)
    return {
        "run_id": run_id,
        "execute_agent": execute_agent,
        "plan": plan,
        "replay_summary": replay_summary,
        "evaluation_summary": evaluation_summary,
        "outputs": outputs,
    }
