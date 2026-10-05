import json
from pathlib import Path


def test_frozen_pairs_cover_safety_and_recall():
    cases = json.loads((Path(__file__).parent / "fixtures/memory_pairs.json").read_text(encoding="utf-8"))
    assert len(cases) == 8
    assert {r["category"] for r in cases} == {
        "number", "negation", "scope", "unit", "exact", "whitespace", "paraphrase"
    }
    assert sum(r["duplicate"] for r in cases) == 4


def test_retrieval_fixture_has_separate_cases_and_valid_labels():
    data = json.loads((Path(__file__).parent / "fixtures/memory_retrieval.json").read_text(encoding="utf-8"))
    ids = {r["id"] for r in data["memories"]}
    assert len(ids) == len(data["memories"]) == 8
    assert len({r["query"] for r in data["cases"]}) == 16
    for split in ("dev", "test"):
        cases = [r for r in data["cases"] if r["split"] == split]
        assert len(cases) == 8 and sum(r["expected"] is None for r in cases) == 2
        assert all(r["expected"] is None or r["expected"] in ids for r in cases)
