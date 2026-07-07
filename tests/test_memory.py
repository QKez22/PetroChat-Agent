from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from petrochat.app.memory import (
    ConversationStore,
    LongTermMemoryStore,
    Mem0MemoryAdapter,
    build_recall_policy,
    fit_prompt_context,
    refresh_conversation_summary,
    recall_long_term_memories,
    validate_memory_candidate,
    write_memory_candidates,
)


def make_memory_test_engine() -> Engine:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE agent_conversation (
                id BIGINT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                title VARCHAR(255),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                expires_at DATETIME,
                deleted_at DATETIME,
                delete_status VARCHAR(50),
                retention_policy VARCHAR(50)
            );
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE agent_message (
                id BIGINT PRIMARY KEY,
                conversation_id BIGINT NOT NULL,
                role VARCHAR(50),
                content TEXT,
                route VARCHAR(50),
                latency_ms INTEGER,
                created_at DATETIME NOT NULL,
                deleted_at DATETIME
            );
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE agent_conversation_summary (
                conversation_id BIGINT PRIMARY KEY,
                summary_text TEXT NOT NULL,
                summarized_until_message_id BIGINT,
                covered_message_id BIGINT,
                source_message_count INTEGER NOT NULL DEFAULT 0,
                summary_version INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE user_memory (
                id BIGINT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                memory_type VARCHAR(64) NOT NULL,
                content TEXT NOT NULL,
                source VARCHAR(64) NOT NULL DEFAULT 'manual',
                confidence REAL NOT NULL DEFAULT 1.0,
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                metadata_json TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                expires_at DATETIME
            );
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE memory_event (
                id BIGINT PRIMARY KEY,
                memory_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                event_type VARCHAR(32) NOT NULL,
                actor_id BIGINT,
                reason VARCHAR(255) NOT NULL DEFAULT '',
                payload_json TEXT,
                created_at DATETIME NOT NULL
            );
            """
        )
    return engine


def test_conversation_store_persists_turns_and_loads_recent_window() -> None:
    store = ConversationStore(make_memory_test_engine())
    session_id = store.ensure_session(None, user_id="1", title="test session")

    store.append_turn(session_id, "first question", "first answer", route="qa", latency_ms=120)
    store.append_turn(session_id, "second question", "second answer", route="general", latency_ms=80)

    recent = store.recent_messages(session_id, turns=1)
    assert [m.role for m in recent] == ["user", "assistant"]
    assert [m.content for m in recent] == ["second question", "second answer"]
    assert store.list_sessions(user_id="1")[0]["message_count"] == 4


def test_conversation_store_soft_deletes_session() -> None:
    engine = make_memory_test_engine()
    store = ConversationStore(engine)
    session_id = store.create_session(user_id="1", title="persistent")
    store.append_turn(session_id, "question", "answer")

    assert store.delete_session(session_id) is True
    assert store.list_sessions(user_id="1") == []
    with engine.connect() as conn:
        deleted_at = conn.execute(
            text("SELECT deleted_at FROM agent_conversation WHERE id = :id"),
            {"id": int(session_id)},
        ).scalar()
    assert deleted_at is not None


def test_conversation_summary_prunes_old_turns(monkeypatch) -> None:
    from petrochat.app.core.config import get_settings

    monkeypatch.setenv("CONVERSATION_SUMMARY_ENABLED", "true")
    monkeypatch.setenv("SHORT_TERM_TURNS", "2")
    monkeypatch.setenv("CONVERSATION_SUMMARY_TRIGGER_TURNS", "2")
    monkeypatch.setenv("CONVERSATION_SUMMARY_MIN_PENDING_MESSAGES", "4")
    monkeypatch.setenv("CONVERSATION_SUMMARY_MAX_CHARS", "600")
    get_settings.cache_clear()

    store = ConversationStore(make_memory_test_engine())
    session_id = store.create_session(user_id="1", title="summary")
    for idx in range(5):
        store.append_turn(
            session_id,
            f"question {idx}: default filter refinery-one active tasks",
            f"answer {idx}: counted active tasks for refinery-one",
        )

    result = refresh_conversation_summary(session_id, store=store, force=True)
    recent = store.recent_messages(session_id, turns=2)

    assert result.updated is True
    assert result.summary is not None
    assert result.pruned_message_count == 6
    assert result.summary.summarized_until_message_id is not None
    assert "refinery-one" in result.summary.summary_text
    assert len(recent) == 4

    get_settings.cache_clear()


def test_conversation_summary_uses_pointer_and_batch_trigger(monkeypatch) -> None:
    from petrochat.app.core.config import get_settings

    monkeypatch.setenv("CONVERSATION_SUMMARY_ENABLED", "true")
    monkeypatch.setenv("SHORT_TERM_TURNS", "2")
    monkeypatch.setenv("CONVERSATION_SUMMARY_MIN_PENDING_MESSAGES", "4")
    monkeypatch.setenv("CONVERSATION_SUMMARY_TRIGGER_TURNS", "20")
    get_settings.cache_clear()

    store = ConversationStore(make_memory_test_engine())
    session_id = store.create_session(user_id="1", title="summary pointer")
    for idx in range(5):
        store.append_turn(session_id, f"question {idx} refinery-one", f"answer {idx} refinery-one")

    first = refresh_conversation_summary(session_id, store=store)
    assert first.updated is True
    assert first.pruned_message_count == 6
    first_pointer = first.summary.summarized_until_message_id if first.summary else None

    for idx in range(5, 6):
        store.append_turn(session_id, f"question {idx} refinery-two", f"answer {idx} refinery-two")
    skipped = refresh_conversation_summary(session_id, store=store)
    assert skipped.updated is False
    assert skipped.pruned_message_count == 0

    for idx in range(6, 8):
        store.append_turn(session_id, f"question {idx} refinery-two", f"answer {idx} refinery-two")
    second = refresh_conversation_summary(session_id, store=store)
    assert second.updated is True
    assert second.pruned_message_count == 6
    assert second.summary is not None
    assert second.summary.summarized_until_message_id != first_pointer

    get_settings.cache_clear()


def test_prompt_context_budget_prunes_injected_history_only(monkeypatch) -> None:
    from petrochat.app.core.config import get_settings

    monkeypatch.setenv("CONTEXT_INPUT_TOKEN_BUDGET", "260")
    monkeypatch.setenv("CONTEXT_SYSTEM_TOKEN_BUDGET", "50")
    monkeypatch.setenv("CONVERSATION_SUMMARY_MAX_TOKENS", "60")
    get_settings.cache_clear()

    history = [
        {"role": "user", "content": "old " + "x" * 400},
        {"role": "assistant", "content": "old answer " + "y" * 400},
        {"role": "user", "content": "recent question"},
        {"role": "assistant", "content": "recent answer"},
    ]
    result = fit_prompt_context(
        question="current question",
        history=history,
        conversation_summary="summary\n" + "\n".join(f"- fact {idx} {'z' * 80}" for idx in range(12)),
        long_term_context="memory " + "m" * 200,
    )

    assert result.dropped_history_count > 0
    assert len(history) == 4
    assert len(result.history) < len(history)
    assert result.estimated_tokens <= 260

    get_settings.cache_clear()


def test_long_term_memory_store_records_lifecycle_events() -> None:
    store = LongTermMemoryStore(make_memory_test_engine())

    item = store.create_memory(
        user_id="1",
        memory_type="preference",
        content="User prefers refinery-one task dashboards.",
        source="manual",
        confidence=0.9,
        metadata={"department": "refinery-one"},
        actor_id="1",
    )
    updated = store.update_memory(
        item.id,
        content="User prefers refinery-one task and instrument dashboards.",
        confidence=0.8,
        actor_id="1",
    )
    disabled = store.disable_memory(item.id, actor_id="1", reason="user requested pause")

    assert updated is not None and updated.confidence == 0.8
    assert disabled is not None and disabled.status == "disabled"
    assert store.list_memories(user_id="1") == []
    assert [m.id for m in store.list_memories(user_id="1", status="all")] == [item.id]
    assert [event.event_type for event in store.list_events(item.id)] == ["created", "updated", "disabled"]


def test_long_term_memory_store_reuses_existing_engine_data() -> None:
    engine = make_memory_test_engine()
    store = LongTermMemoryStore(engine)
    item = store.create_memory(user_id="1", memory_type="business_context", content="User owns refinery-one work.")

    reopened = LongTermMemoryStore(engine)
    memories = reopened.list_memories(user_id="1")
    assert len(memories) == 1
    assert memories[0].id == item.id


class FakeMem0Client:
    def __init__(self, *, memory_id: str | None = None, candidate: str | None = None) -> None:
        self.memory_id = memory_id
        self.candidate = candidate or "Default to refinery-one active tasks."
        self.add_calls = []
        self.update_calls = []
        self.delete_calls = []
        self.reset_calls = 0

    def add(self, messages, **kwargs):
        self.add_calls.append((messages, kwargs))
        if kwargs.get("infer") is True:
            return {"results": [{"id": "candidate-1", "memory": self.candidate, "score": 0.86}]}
        return {"results": [{"id": "active-1", "memory": messages, "event": "ADD"}]}

    def search(self, **kwargs):
        return {
            "results": [
                {
                    "id": "active-hit",
                    "memory": "Default to refinery-one active tasks.",
                    "score": 0.91,
                    "metadata": {
                        "stage": "active",
                        "status": "active",
                        "memory_type": "query_filter",
                        "petrochat_memory_id": self.memory_id,
                    },
                }
            ]
        }

    def get_all(self, **kwargs):
        filters = kwargs.get("filters", {})
        return {
            "results": [
                {
                    "id": "active-existing",
                    "memory": "Default to refinery-one active tasks.",
                    "metadata": {"petrochat_memory_id": filters.get("petrochat_memory_id")},
                }
            ]
        }

    def update(self, memory_id, data=None, metadata=None):
        self.update_calls.append((memory_id, data, metadata))
        return {"id": memory_id}

    def delete(self, memory_id):
        self.delete_calls.append(memory_id)
        return {"id": memory_id}

    def reset(self):
        self.reset_calls += 1


def test_mem0_adapter_uses_candidate_and_active_collections() -> None:
    active_client = FakeMem0Client()
    candidate_client = FakeMem0Client(candidate="User prefers default active refinery-one tasks.")
    adapter = Mem0MemoryAdapter(active_client, candidate_client=candidate_client, enabled=True)
    item = LongTermMemoryStore(make_memory_test_engine()).create_memory(
        user_id="1",
        memory_type="query_filter",
        content="Default to refinery-one active tasks.",
        source="manual",
        metadata={"department": "refinery-one"},
    )

    candidates = adapter.extract_candidates(
        messages=[{"role": "user", "content": "Remember active refinery-one tasks by default."}],
        user_id="1",
    )
    adapter.sync_created(item)
    adapter.sync_updated(item)
    adapter.sync_removed(item)

    assert candidates[0].content == "User prefers default active refinery-one tasks."
    assert candidate_client.add_calls[0][1]["infer"] is True
    assert active_client.add_calls[0][1]["infer"] is False
    assert active_client.update_calls[0][0] == "active-existing"
    assert active_client.delete_calls == ["active-existing"]


def test_recall_uses_mem0_ids_but_validates_mysql_records(monkeypatch) -> None:
    engine = make_memory_test_engine()
    store = LongTermMemoryStore(engine)
    item = store.create_memory(
        user_id="1",
        memory_type="query_filter",
        content="Default to refinery-one active tasks.",
        confidence=0.88,
    )
    adapter = Mem0MemoryAdapter(FakeMem0Client(memory_id=item.id), enabled=True)

    from petrochat.app.memory import context as context_module

    monkeypatch.setattr(context_module, "get_mem0_memory_adapter", lambda: adapter)
    memories, context = recall_long_term_memories(
        user_id="1",
        question="Count active tasks.",
        limit=2,
        store=store,
        route_hint="sql",
    )

    assert len(memories) == 1
    assert memories[0].memory_id == item.id
    assert memories[0].recall_source == "mem0"
    assert memories[0].score == 0.91
    assert "[memory:" in context


def test_write_memory_candidates_uses_mem0_candidate_then_mysql(monkeypatch) -> None:
    store = LongTermMemoryStore(make_memory_test_engine())
    adapter = Mem0MemoryAdapter(
        FakeMem0Client(),
        candidate_client=FakeMem0Client(candidate="Default to refinery-one active tasks."),
        enabled=True,
    )

    from petrochat.app.memory import context as context_module

    monkeypatch.setattr(context_module, "get_mem0_memory_adapter", lambda: adapter)
    question = "Remember: default to refinery-one active tasks."
    written = write_memory_candidates(user_id="1", question=question, route="sql", store=store)
    duplicated = write_memory_candidates(user_id="1", question=question, route="sql", store=store)
    ignored = write_memory_candidates(user_id="default", question=question, route="sql", store=store)

    assert len(written) == 1
    assert duplicated == []
    assert ignored == []
    memories = store.list_memories(user_id="1")
    assert len(memories) == 1
    assert memories[0].source == "mem0_infer"
    assert memories[0].memory_type == "query_filter"
    assert memories[0].metadata["extractor"] == "mem0_infer"


def test_memory_policy_limits_sql_and_rejects_non_memory_content() -> None:
    sql_policy = build_recall_policy("Count active task quantity.")
    qa_policy = build_recall_policy("What is the equipment grading standard?")

    assert sql_policy.route in {"sql", "general"}
    assert sql_policy.memory_types >= {"preference", "query_filter"}
    assert qa_policy.use_mem0 is False

    validate_memory_candidate("preference", "Default to refinery-one tasks.")
    try:
        validate_memory_candidate("domain_fact", "ITPM standard says equipment must be graded.")
    except ValueError as exc:
        assert "unsupported memory_type" in str(exc)
    else:
        raise AssertionError("domain_fact must be rejected")

    try:
        validate_memory_candidate("preference", "My API_KEY is abc.")
    except ValueError as exc:
        assert "sensitive" in str(exc)
    else:
        raise AssertionError("secret-like memory must be rejected")
