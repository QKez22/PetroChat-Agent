from __future__ import annotations

from petrochat.app.memory import ConversationStore


def test_conversation_store_persists_turns_and_loads_recent_window(tmp_path) -> None:
    db_path = tmp_path / "sessions.sqlite3"
    store = ConversationStore(db_path)
    session_id = store.ensure_session(None, user_id="u1", title="测试会话")

    store.append_turn(session_id, "第一问", "第一答", route="qa", latency_ms=120)
    store.append_turn(session_id, "第二问", "第二答", route="general", latency_ms=80)

    recent = store.recent_messages(session_id, turns=1)
    assert [m.role for m in recent] == ["user", "assistant"]
    assert [m.content for m in recent] == ["第二问", "第二答"]

    sessions = store.list_sessions(user_id="u1")
    assert len(sessions) == 1
    assert sessions[0]["message_count"] == 4


def test_conversation_store_can_reopen_existing_sqlite_file(tmp_path) -> None:
    db_path = tmp_path / "sessions.sqlite3"
    store = ConversationStore(db_path)
    session_id = store.create_session(user_id="u1", title="持久化")
    store.append_turn(session_id, "问题", "答案")

    reopened = ConversationStore(db_path)
    messages = reopened.list_messages(session_id)
    assert [m.content for m in messages] == ["问题", "答案"]
