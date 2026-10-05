import json
from pathlib import Path

import pytest
from sqlalchemy import event

from test_memory import make_memory_test_engine
from petrochat.app.memory.long_term import LongTermMemoryStore
from petrochat.app.memory.policy import _is_duplicate
from petrochat.app.memory.validity import normalize_expiry


def test_no_dangerous_fuzzy_merge():
    cases = json.loads((Path(__file__).parent / "fixtures/memory_pairs.json").read_text(encoding="utf-8"))
    for case in cases:
        if not case["duplicate"] or case["category"] in {"exact", "whitespace"}:
            assert _is_duplicate(case["new"], {case["old"]}) == case["duplicate"]


def test_batch_recall_is_one_select_and_filters_lifecycle():
    engine = make_memory_test_engine()
    store = LongTermMemoryStore(engine)
    good = store.create_memory(user_id="1", memory_type="preference", content="Preferred short answers")
    expired = store.create_memory(user_id="1", memory_type="preference", content="Expired preference", expires_at="2000-01-01")
    foreign = store.create_memory(user_id="2", memory_type="preference", content="Other user preference")
    disabled = store.create_memory(user_id="1", memory_type="preference", content="Disabled preference")
    store.disable_memory(disabled.id)
    calls = []
    event.listen(engine, "before_cursor_execute", lambda c, cur, sql, p, ctx, many: calls.append(sql))
    result = store.get_memories_for_recall(user_id="1", memory_types={"preference"},
        ids=[good.id, expired.id, foreign.id, disabled.id, "bad", good.id])
    assert [i.id for i in result] == [good.id]
    assert len(calls) == 1
    assert store.get_memories_for_recall(user_id="1", memory_types={"preference"}, ids=[]) == []
    assert len(calls) == 1


def test_expiry_update_clear_and_index_exclusion():
    store = LongTermMemoryStore(make_memory_test_engine())
    item = store.create_memory(user_id="1", memory_type="preference", content="Short answers preferred")
    store.update_memory(item.id, expires_at="2000-01-01T08:00:00+08:00")
    assert store.get_memory(item.id).expires_at == "2000-01-01 00:00:00"
    assert store.list_active_memories_for_index() == []
    assert store.get_memories_for_recall(user_id="1", memory_types={"preference"}) == []
    store.update_memory(item.id, expires_at=None)
    assert len(store.list_active_memories_for_index()) == 1
    with pytest.raises(ValueError):
        store.update_memory(item.id, expires_at="tomorrow")
    assert normalize_expiry("2030-01-01T08:00:00+08:00") == "2030-01-01 00:00:00"
