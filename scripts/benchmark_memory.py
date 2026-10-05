"""Frozen developer-authored pairs; not an end-to-end memory quality benchmark."""
import json
from pathlib import Path

from petrochat.app.memory.policy import _is_duplicate


def evaluate() -> dict:
    path = Path(__file__).resolve().parents[1] / "tests/fixtures/memory_pairs.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    results = [
        {**case, "prediction": _is_duplicate(case["new"].strip(), {case["old"]})}
        for case in cases
    ]
    return {
        "cases": len(results),
        "correct": sum(r["prediction"] == r["duplicate"] for r in results),
        "false_merges": sum(r["prediction"] and not r["duplicate"] for r in results),
        "missed_duplicates": sum(not r["prediction"] and r["duplicate"] for r in results),
        "results": results,
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
