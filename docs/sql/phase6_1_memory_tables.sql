-- Phase 6.1 long-term memory tables for PetroChat-Agent.
-- Run these statements in the same MySQL schema used by the application.

CREATE TABLE IF NOT EXISTS user_memory (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    memory_type VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    source VARCHAR(64) NOT NULL DEFAULT 'manual',
    confidence DECIMAL(5,4) NOT NULL DEFAULT 1.0000,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    metadata_json JSON,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    expires_at DATETIME,
    INDEX idx_user_memory_user_status (user_id, status, updated_at),
    INDEX idx_user_memory_type_status (memory_type, status)
);

CREATE TABLE IF NOT EXISTS memory_event (
    id BIGINT PRIMARY KEY,
    memory_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    actor_id BIGINT,
    reason VARCHAR(255) NOT NULL DEFAULT '',
    payload_json JSON,
    created_at DATETIME NOT NULL,
    INDEX idx_memory_event_memory_created (memory_id, created_at),
    CONSTRAINT fk_memory_event_memory
        FOREIGN KEY (memory_id) REFERENCES user_memory(id)
        ON DELETE CASCADE
);

-- Existing application tables expected by the MySQL-backed conversation store.
-- You already have these tables; keep this block only for schema verification.

CREATE TABLE IF NOT EXISTS agent_message (
    id BIGINT PRIMARY KEY,
    conversation_id BIGINT NOT NULL,
    role VARCHAR(50),
    content TEXT,
    created_at DATETIME NOT NULL,
    deleted_at DATETIME,
    INDEX idx_agent_message_conversation_created (conversation_id, created_at)
);

-- If your existing agent_message table does not have deleted_at yet, run:
-- ALTER TABLE agent_message ADD COLUMN deleted_at DATETIME;
-- CREATE INDEX idx_agent_message_conversation_created
--     ON agent_message(conversation_id, created_at);
