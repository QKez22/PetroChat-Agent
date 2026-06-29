"""Run or plan a sanitized real-agent baseline replay.

Default behavior is plan-only and does not call LLMs. Add --execute-agent to
invoke the current LangGraph agent against the selected private Golden Set
slice.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from petrochat.app.core.config import PROJECT_ROOT
from petrochat.app.evaluation.baseline import parse_scenario_targets, run_agent_baseline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan or run Phase 10.2 agent baseline replay.")
    parser.add_argument(
        "--golden-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "ducuments" / "agent_memory_golden_set",
        help="Local private Golden Set directory. This directory is ignored by git.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "eval_results" / "agent_baseline",
        help="Ignored local output directory for baseline artifacts.",
    )
    parser.add_argument(
        "--scenario-target",
        action="append",
        default=None,
        help="Scenario dialogue target in name=count format. Can be repeated.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=20,
        help="Maximum turns to replay when --execute-agent is used.",
    )
    parser.add_argument(
        "--eval-user-id",
        default="0",
        help="Numeric user_id used for agent replay memory isolation.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional run id written to prediction rows and summary.",
    )
    parser.add_argument(
        "--execute-agent",
        action="store_true",
        help="Actually call the current LangGraph agent. Without this flag, only write a plan.",
    )
    parser.add_argument(
        "--fail-on-gate",
        action="store_true",
        help="Exit with code 2 when executed quality gate status is fail.",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Print sanitized baseline summary JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.max_turns <= 0:
        raise ValueError("--max-turns must be positive")

    result = run_agent_baseline(
        golden_dir=args.golden_dir,
        out_dir=args.out_dir,
        scenario_targets=parse_scenario_targets(args.scenario_target),
        max_turns=args.max_turns,
        eval_user_id=args.eval_user_id,
        run_id=args.run_id,
        execute_agent=args.execute_agent,
    )

    gate = (result.get("evaluation_summary") or {}).get("quality_gate") or {}
    payload = {
        "run_id": result["run_id"],
        "execute_agent": result["execute_agent"],
        "selected_dialogues": result["plan"]["selectedDialogueCount"],
        "effective_turn_limit": result["plan"]["effectiveTurnLimit"],
        "scenario_counts": result["plan"]["scenarioCounts"],
        "quality_gate": {
            "status": gate.get("status", "not-run"),
            "label": gate.get("label", "未运行"),
            "failedCount": gate.get("failedCount", 0),
            "warningCount": gate.get("warningCount", 0),
        },
        "outputs": result["outputs"],
    }

    if args.print_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        mode = "executed" if args.execute_agent else "plan-only"
        print("Agent baseline complete")
        print(f"- mode: {mode}")
        print(f"- run_id: {payload['run_id']}")
        print(f"- selected_dialogues: {payload['selected_dialogues']}")
        print(f"- effective_turn_limit: {payload['effective_turn_limit']}")
        print(f"- quality_gate: {payload['quality_gate']['status']}")
        for name, path in payload["outputs"].items():
            print(f"- {name}: {path}")

    if args.fail_on_gate and gate.get("status") == "fail":
        sys.exit(2)


if __name__ == "__main__":
    main()
