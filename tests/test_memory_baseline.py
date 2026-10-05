import json
from pathlib import Path


def test_frozen_pairs_cover_safety_and_recall():
    cases = json.loads((Path(__file__).parent / "fixtures/memory_pairs.json").read_text(encoding="utf-8"))
    assert len(cases) == 8
    assert {r["category"] for r in cases} == {
        "number", "negation", "scope", "unit", "exact", "whitespace", "paraphrase"
    }
    assert sum(r["duplicate"] for r in cases) == 4
