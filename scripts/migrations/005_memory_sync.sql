-- Run as database administrator. Verified local database/account below;
-- change them first for other deployments. No business-table grants.
USE timing_task;
CREATE TABLE IF NOT EXISTS agent_memory_sync (
    memory_id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    generation INT NOT NULL,
    pending INT NOT NULL,
    attempts INT NOT NULL,
    due_at DOUBLE NOT NULL,
    lease_until DOUBLE NOT NULL,
    lease_token VARCHAR(64) NOT NULL,
    last_error VARCHAR(120) NOT NULL,
    INDEX idx_memory_sync_due (pending, due_at, lease_until)
);
GRANT SELECT, INSERT, UPDATE, DELETE ON timing_task.agent_memory_sync TO 'petrochat_app'@'%';
