from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from petrochat.app.retention import RetentionCleanupService, RetentionConfig


def make_retention_engine() -> Engine:
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
            CREATE TABLE agent_tool_log (
                id BIGINT PRIMARY KEY,
                conversation_id BIGINT,
                user_id BIGINT,
                tool_name VARCHAR(100),
                input_summary TEXT,
                output_summary TEXT,
                status VARCHAR(50),
                error_message TEXT,
                created_at DATETIME NOT NULL,
                expires_at DATETIME
            );
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE agent_audit_log (
                id BIGINT PRIMARY KEY,
                user_id BIGINT,
                action_type VARCHAR(100),
                target_type VARCHAR(100),
                target_id VARCHAR(100),
                action_detail TEXT,
                ip_address VARCHAR(100),
                created_at DATETIME NOT NULL
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


def seed_retention_data(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO agent_conversation(
                    id, user_id, title, created_at, updated_at, expires_at,
                    deleted_at, delete_status, retention_policy
                )
                VALUES
                    (1, 1, 'old active', '2025-01-01 00:00:00', '2025-01-01 00:00:00',
                     NULL, NULL, 'active', 'conversation_180d'),
                    (2, 1, 'already deleted', '2025-01-01 00:00:00', '2025-01-02 00:00:00',
                     NULL, '2026-04-01 00:00:00', 'user_deleted', 'conversation_180d'),
                    (3, 1, 'fresh', '2026-06-01 00:00:00', '2026-06-20 00:00:00',
                     NULL, NULL, 'active', 'conversation_180d')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO agent_message(id, conversation_id, role, content, created_at, deleted_at)
                VALUES
                    (11, 1, 'user', 'old active message', '2025-01-01 00:00:00', NULL),
                    (21, 2, 'user', 'deleted message', '2025-01-01 00:00:00', NULL),
                    (31, 3, 'user', 'fresh message', '2026-06-20 00:00:00', NULL)
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO agent_tool_log(
                    id, conversation_id, user_id, tool_name, input_summary,
                    output_summary, status, error_message, created_at, expires_at
                )
                VALUES
                    (101, 1, 1, 'retrieve_specs', 'old', 'old', 'ok', '', '2025-01-01 00:00:00', NULL),
                    (102, 3, 1, 'retrieve_specs', 'fresh', 'fresh', 'ok', '', '2026-06-20 00:00:00', NULL)
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO agent_audit_log(
                    id, user_id, action_type, target_type, target_id,
                    action_detail, ip_address, created_at
                )
                VALUES
                    (201, 1, 'old_audit', 'system', 'old', 'old', '127.0.0.1', '2022-01-01 00:00:00'),
                    (202, 1, 'fresh_audit', 'system', 'fresh', 'fresh', '127.0.0.1', '2026-06-20 00:00:00')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO user_memory(
                    id, user_id, memory_type, content, source, confidence, status,
                    metadata_json, created_at, updated_at, expires_at
                )
                VALUES
                    (301, 1, 'preference', 'expired memory', 'manual', 1.0, 'active',
                     '{}', '2026-01-01 00:00:00', '2026-01-01 00:00:00', '2026-06-01 00:00:00'),
                    (302, 1, 'preference', 'fresh memory', 'manual', 1.0, 'active',
                     '{}', '2026-06-20 00:00:00', '2026-06-20 00:00:00', NULL)
                """
            )
        )


def test_retention_cleanup_dry_run_does_not_mutate() -> None:
    engine = make_retention_engine()
    seed_retention_data(engine)
    service = RetentionCleanupService(engine)
    result = service.run(
        dry_run=True,
        now=datetime(2026, 6, 26, tzinfo=UTC),
        config=RetentionConfig(),
    )

    assert result.affected["conversations_soft_deleted"] == 1
    assert result.affected["conversations_physical_deleted"] == 1
    assert result.affected["messages_physical_deleted"] == 1
    assert result.affected["tool_logs_deleted"] == 1
    assert result.affected["audit_logs_deleted"] == 1
    assert result.affected["memories_disabled"] == 1

    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM agent_conversation")).scalar() == 3
        assert conn.execute(text("SELECT COUNT(*) FROM agent_tool_log")).scalar() == 2
        assert conn.execute(text("SELECT status FROM user_memory WHERE id = 301")).scalar() == "active"
        assert conn.execute(text("SELECT COUNT(*) FROM memory_event")).scalar() == 0


def test_retention_cleanup_execute_mutates_and_audits() -> None:
    engine = make_retention_engine()
    seed_retention_data(engine)
    service = RetentionCleanupService(engine)
    result = service.run(
        dry_run=False,
        now=datetime(2026, 6, 26, tzinfo=UTC),
        config=RetentionConfig(),
        actor_id="1",
        reason="unit test retention",
    )

    assert result.audit_log_id
    assert result.affected["conversations_soft_deleted"] == 1
    assert result.affected["conversations_physical_deleted"] == 1
    assert result.affected["tool_logs_deleted"] == 1
    assert result.affected["memories_disabled"] == 1

    with engine.connect() as conn:
        assert conn.execute(text("SELECT deleted_at FROM agent_conversation WHERE id = 1")).scalar()
        assert conn.execute(text("SELECT COUNT(*) FROM agent_conversation WHERE id = 2")).scalar() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM agent_message WHERE conversation_id = 2")).scalar() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM agent_tool_log WHERE id = 101")).scalar() == 0
        assert conn.execute(text("SELECT status FROM user_memory WHERE id = 301")).scalar() == "disabled"
        assert conn.execute(text("SELECT COUNT(*) FROM memory_event WHERE memory_id = 301")).scalar() == 1
        assert conn.execute(
            text("SELECT COUNT(*) FROM agent_audit_log WHERE action_type = 'retention_cleanup'")
        ).scalar() == 1
