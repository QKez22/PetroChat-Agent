-- Administrator only. Local deployment: timing_task / petrochat_app@%.
-- Application-owned report tables only; no business-table writes or global grants.
USE timing_task;

CREATE TABLE IF NOT EXISTS agent_report_task (
    id VARCHAR(64) PRIMARY KEY,
    user_id BIGINT NOT NULL,
    workflow_version VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    revision INT NOT NULL DEFAULT 0,
    question TEXT NOT NULL,
    state_json JSON NOT NULL,
    lease_token VARCHAR(64) NOT NULL DEFAULT '',
    lease_until DOUBLE NOT NULL DEFAULT 0,
    attempts INT NOT NULL DEFAULT 0,
    due_at DOUBLE NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    INDEX idx_report_owner (user_id, updated_at),
    INDEX idx_report_pending (status, due_at, lease_until)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS agent_report_event (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    revision INT NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload JSON NOT NULL,
    created_at DATETIME(6) NOT NULL,
    INDEX idx_report_event (task_id, id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS agent_report_artifact (
    id VARCHAR(64) PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    revision INT NOT NULL,
    kind VARCHAR(32) NOT NULL,
    storage_key VARCHAR(255) NOT NULL,
    sha256 CHAR(64) NOT NULL,
    byte_size BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL,
    UNIQUE KEY uq_report_artifact (task_id, revision, kind)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS agent_report_checkpoint (
    thread_id VARCHAR(64) NOT NULL,
    namespace VARCHAR(255) NOT NULL,
    checkpoint_id VARCHAR(64) NOT NULL,
    parent_id VARCHAR(64),
    data_type VARCHAR(32) NOT NULL,
    data LONGBLOB NOT NULL,
    meta_type VARCHAR(32) NOT NULL,
    metadata LONGBLOB NOT NULL,
    PRIMARY KEY (thread_id, namespace, checkpoint_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS agent_report_write (
    thread_id VARCHAR(64) NOT NULL,
    namespace VARCHAR(255) NOT NULL,
    checkpoint_id VARCHAR(64) NOT NULL,
    task_id VARCHAR(64) NOT NULL,
    write_index INT NOT NULL,
    channel VARCHAR(255) NOT NULL,
    task_path VARCHAR(1024) NOT NULL,
    data_type VARCHAR(32) NOT NULL,
    data LONGBLOB NOT NULL,
    PRIMARY KEY (thread_id, namespace, checkpoint_id, task_id, write_index)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;

GRANT SELECT, INSERT, UPDATE, DELETE ON timing_task.agent_report_task TO 'petrochat_app'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON timing_task.agent_report_event TO 'petrochat_app'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON timing_task.agent_report_artifact TO 'petrochat_app'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON timing_task.agent_report_checkpoint TO 'petrochat_app'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON timing_task.agent_report_write TO 'petrochat_app'@'%';
