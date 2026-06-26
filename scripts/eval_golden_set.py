"""Run Golden Set profiling and optional prediction evaluation.

Example:
    uv run python scripts/eval_golden_set.py
    uv run python scripts/eval_golden_set.py --predictions data/eval_results/predictions.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from petrochat.app.core.config import PROJECT_ROOT
from petrochat.app.evaluation import evaluate_golden_set


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate PetroChat Golden Set contracts.")
    parser.add_argument(
        "--golden-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "ducuments" / "agent_memory_golden_set",
        help="Local private Golden Set directory. This directory is ignored by git.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "eval_results",
        help="Directory for generated JSON/Markdown summaries.",
    )
    parser.add_argument(
        "--predictions",
        "--prediction-path",
        type=Path,
        default=None,
        help="Optional JSONL file with agent predictions for metric scoring.",
    )
    parser.add_argument(
        "--fail-on-gate",
        action="store_true",
        help="Exit with code 2 when the quality gate status is fail.",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Print the full summary JSON to stdout.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = evaluate_golden_set(
        golden_dir=args.golden_dir,
        out_dir=args.out_dir,
        prediction_path=args.predictions,
    )
    if args.print_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    profile = result["dataset_profile"]
    sql = result["sql_contract"]
    memory = result["memory_contract"]
    rag = result["rag_contract"]
    gate = result["quality_gate"]
    print("Golden Set evaluation complete")
    print(f"- dialogues: {profile['dialogue_count']}")
    print(f"- turns: {profile['turn_count']}")
    print(f"- SQL template valid rate: {sql['template_valid_rate']}")
    print(f"- memory use turns: {memory['requires_memory_use_turns']}")
    print(f"- RAG evidence rows: {rag['evidence_count']}")
    print(f"- quality gate: {gate['status']} ({gate['label']})")
    print(f"- outputs: {result['outputs']['json']}")
    if args.fail_on_gate and gate["status"] == "fail":
        sys.exit(2)


if __name__ == "__main__":
    main()
