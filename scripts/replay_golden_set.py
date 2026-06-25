"""Generate prediction JSONL from the private Golden Set.

Default mode is "oracle", which does not call LLMs and only verifies the
prediction/evaluation pipeline. Use "--mode agent" explicitly for real agent
replay against DeepSeek, Chroma and MySQL.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from petrochat.app.core.config import PROJECT_ROOT
from petrochat.app.evaluation import evaluate_golden_set, generate_predictions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay Golden Set into prediction JSONL.")
    parser.add_argument(
        "--golden-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "ducuments" / "agent_memory_golden_set",
        help="Local private Golden Set directory. This directory is ignored by git.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "eval_results" / "predictions.jsonl",
        help="Prediction JSONL output path.",
    )
    parser.add_argument(
        "--mode",
        choices=["oracle", "agent"],
        default="oracle",
        help="oracle = no model calls; agent = invoke the current LangGraph agent.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of turns to replay. Agent mode defaults to 5 for safe smoke runs.",
    )
    parser.add_argument(
        "--scenario-type",
        default=None,
        help="Only replay turns with this scenario_type.",
    )
    parser.add_argument(
        "--dialogue-id",
        action="append",
        default=None,
        help="Only replay a specific dialogue_id. Can be provided multiple times.",
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
        "--summary-output",
        type=Path,
        default=None,
        help="Optional replay summary JSON path.",
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Run Golden Set evaluation after writing predictions.",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Print replay summary JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    limit = args.limit
    if args.mode == "agent" and limit is None:
        limit = 5
    summary_output = args.summary_output
    if summary_output is None and args.mode == "agent":
        summary_output = args.output.with_suffix(".summary.json")

    summary = generate_predictions(
        golden_dir=args.golden_dir,
        output_path=args.output,
        mode=args.mode,
        limit=limit,
        scenario_type=args.scenario_type,
        dialogue_ids=set(args.dialogue_id or []),
        eval_user_id=args.eval_user_id,
        run_id=args.run_id,
        summary_path=summary_output,
    )
    if args.evaluate:
        eval_summary = evaluate_golden_set(
            golden_dir=args.golden_dir,
            out_dir=args.output.parent,
            prediction_path=args.output,
        )
        summary["evaluation"] = eval_summary.get("prediction_metrics", {})

    if args.print_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    print("Golden Set replay complete")
    print(f"- run_id: {summary['run_id']}")
    print(f"- mode: {summary['mode']}")
    print(f"- predictions: {summary['prediction_count']}")
    print(f"- success_rate: {summary['prediction_summary']['success_rate']}")
    print(f"- error_count: {summary['prediction_summary']['error_count']}")
    print(f"- output: {summary['output_path']}")
    if summary.get("summary_path"):
        print(f"- summary: {summary['summary_path']}")
    if args.evaluate:
        print(f"- evaluation: {summary['evaluation']}")


if __name__ == "__main__":
    main()
