-- Phase 11 migration for users who already created agent_conversation_summary
-- with the old covered_message_id pointer.
-- MySQL 8.x / utf8mb4

ALTER TABLE agent_conversation_summary
    ADD COLUMN summarized_until_message_id BIGINT NULL AFTER summary_text;

UPDATE agent_conversation_summary
SET summarized_until_message_id = covered_message_id
WHERE summarized_until_message_id IS NULL
  AND covered_message_id IS NOT NULL;

CREATE INDEX idx_conversation_summary_pointer
    ON agent_conversation_summary (summarized_until_message_id);

ALTER TABLE agent_conversation_summary
    ADD CONSTRAINT fk_conversation_summary_pointer
        FOREIGN KEY (summarized_until_message_id) REFERENCES agent_message(id)
        ON DELETE SET NULL;
