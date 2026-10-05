import pytest
from test_memory import make_memory_test_engine
from petrochat.app.memory.long_term import LongTermMemoryStore
from petrochat.app.memory.preferences import Preference, explicit_preference
from petrochat.app.memory.versions import PreferenceConflict, put_preference


def test_revisions_preserve_old_values_and_reject_stale_writes():
    store = LongTermMemoryStore(make_memory_test_engine())
    p = Preference(key="query.default_tonnage", value="100000", unit="吨")
    first = put_preference(store, user_id="1", preference=p, expected_revision=0)
    same = put_preference(store, user_id="1", preference=p, expected_revision=1)
    assert first.id == same.id and same.metadata["revision"] == 1
    changed = put_preference(store, user_id="1", preference=p.model_copy(update={"value":"200000"}), expected_revision=1)
    assert changed.metadata["revision"] == 2
    assert len(store.list_memories(user_id="1")) == 1
    history = store.list_events(first.id)
    assert history[-1].payload["before"]["metadata"]["value"] == "100000"
    assert history[-1].payload["after"]["metadata"]["value"] == "200000"
    with pytest.raises(PreferenceConflict):
        put_preference(store, user_id="1", preference=p, expected_revision=1)
    with pytest.raises(ValueError):
        store.update_memory(first.id, content="Bypass revision")


def test_scope_user_and_deleted_preference_isolation():
    store = LongTermMemoryStore(make_memory_test_engine())
    p = Preference(key="answer.verbosity", value="concise")
    a = put_preference(store, user_id="1", preference=p, expected_revision=0)
    b = put_preference(store, user_id="2", preference=p, expected_revision=0)
    c = put_preference(store, user_id="1", preference=p.model_copy(update={"scope":"项目A"}), expected_revision=0)
    assert len({a.id,b.id,c.id}) == 3
    store.delete_memory(a.id)
    with pytest.raises(PreferenceConflict):
        put_preference(store, user_id="1", preference=p, expected_revision=1)


def test_explicit_parser_is_conservative():
    assert explicit_preference("以后默认查询10万吨的任务").value == "100000"
    assert explicit_preference("以后默认查询20万吨的任务").value == "200000"
    assert explicit_preference("以后回答详细一点").value == "detailed"
    for value in ["以后不默认查询10万吨的任务", "项目B以后默认查询10万吨的任务", "默认查10万吨还是20万吨", "默认查10万吨，压力是5MPa"]:
        assert explicit_preference(value) is None


def test_preference_api_conflict_and_invalid_value(monkeypatch):
    from test_api import client, auth_headers
    from petrochat.app.api import memory as api
    store = LongTermMemoryStore(make_memory_test_engine())
    monkeypatch.setattr(api, "get_long_term_memory_store", lambda: store)
    payload = {"preference":{"key":"query.default_tonnage","value":"100000","unit":"吨"}, "expected_revision":0}
    assert client.put("/api/memory/preferences", json=payload).status_code == 401
    first = client.put("/api/memory/preferences", json=payload, headers=auth_headers())
    assert first.status_code == 200 and first.json()["metadata"]["revision"] == 1
    assert client.put("/api/memory/preferences", json=payload, headers=auth_headers()).status_code == 409
    payload["preference"]["value"] = "not-a-number"
    assert client.put("/api/memory/preferences", json=payload, headers=auth_headers()).status_code == 422
