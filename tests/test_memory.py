from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from petrochat.app.memory import ConversationStore, LongTermMemoryStore


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
                created_at DATETIME NOT NULL,
                deleted_at DATETIME
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
    engine = make_memory_test_engine()
    store = ConversationStore(engine)
    session_id = store.ensure_session(None, user_id="1", title="测试会话")

    store.append_turn(session_id, "第一问", "第一答", route="qa", latency_ms=120)
    store.append_turn(session_id, "第二问", "第二答", route="general", latency_ms=80)

    recent = store.recent_messages(session_id, turns=1)
    assert [m.role for m in recent] == ["user", "assistant"]
    assert [m.content for m in recent] == ["第二问", "第二答"]

    sessions = store.list_sessions(user_id="1")
    assert len(sessions) == 1
    assert sessions[0]["message_count"] == 4


def test_conversation_store_soft_deletes_session() -> None:
    engine = make_memory_test_engine()
    store = ConversationStore(engine)
    session_id = store.create_session(user_id="1", title="持久化")
    store.append_turn(session_id, "问题", "答案")

    assert store.delete_session(session_id) is True
    assert store.list_sessions(user_id="1") == []
    with engine.connect() as conn:
        deleted_at = conn.execute(
            text("SELECT deleted_at FROM agent_conversation WHERE id = :id"),
            {"id": int(session_id)},
        ).scalar()
    assert deleted_at is not None


def test_long_term_memory_store_records_lifecycle_events() -> None:
    engine = make_memory_test_engine()
    store = LongTermMemoryStore(engine)

    item = store.create_memory(
        user_id="1",
        memory_type="preference",
        content="用户常看炼油一部的动设备任务",
        source="manual",
        confidence=0.9,
        metadata={"department": "炼油一部"},
        actor_id="1",
    )
    assert item.status == "active"
    assert item.metadata["department"] == "炼油一部"

    updated = store.update_memory(
        item.id,
        content="用户常看炼油一部的动设备和仪表任务",
        confidence=0.8,
        actor_id="1",
    )
    assert updated is not None
    assert updated.confidence == 0.8

    disabled = store.disable_memory(item.id, actor_id="1", reason="用户要求暂停")
    assert disabled is not None
    assert disabled.status == "disabled"

    active = store.list_memories(user_id="1")
    assert active == []

    all_items = store.list_memories(user_id="1", status="all")
    assert [m.id for m in all_items] == [item.id]

    events = store.list_events(item.id)
    assert [event.event_type for event in events] == ["created", "updated", "disabled"]
    assert events[-1].reason == "用户要求暂停"


def test_long_term_memory_store_reuses_existing_engine_data() -> None:
    engine = make_memory_test_engine()
    store = LongTermMemoryStore(engine)
    item = store.create_memory(user_id="1", memory_type="business_context", content="默认统计运行中事务")

    reopened = LongTermMemoryStore(engine)
    memories = reopened.list_memories(user_id="1")
    assert len(memories) == 1
    assert memories[0].id == item.id
    assert memories[0].content == "默认统计运行中事务"
