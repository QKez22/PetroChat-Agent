-- Phase 11 conversation rolling-summary table for PetroChat-Agent.
-- MySQL 8.x / utf8mb4

CREATE TABLE IF NOT EXISTS agent_conversation_summary (
    conversation_id BIGINT PRIMARY KEY,
    summary_text MEDIUMTEXT NOT NULL,
    summarized_until_message_id BIGINT,
    covered_message_id BIGINT COMMENT 'Deprecated compatibility alias; use summarized_until_message_id.',
    source_message_count INT NOT NULL DEFAULT 0,
    summary_version INT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    INDEX idx_conversation_summary_updated (updated_at),
    INDEX idx_conversation_summary_pointer (summarized_until_message_id),
    CONSTRAINT fk_conversation_summary_conversation
        FOREIGN KEY (conversation_id) REFERENCES agent_conversation(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_conversation_summary_pointer
        FOREIGN KEY (summarized_until_message_id) REFERENCES agent_message(id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
