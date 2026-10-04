-- 由数据库管理员执行；应用账号不需要 CREATE 或全库写权限。
-- 当前本地环境已核实：database=timing_task，应用账号=petrochat_app@%。
-- 其他部署请先调整数据库名和账号，勿授予业务表写权限。
USE timing_task;

CREATE TABLE IF NOT EXISTS agent_rag_manifest (
    snapshot_id VARCHAR(64) NOT NULL PRIMARY KEY,
    collection_name VARCHAR(128) NOT NULL,
    payload JSON NOT NULL
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS agent_rag_active (
    name VARCHAR(32) NOT NULL PRIMARY KEY,
    snapshot_id VARCHAR(64) NOT NULL
) CHARACTER SET utf8mb4;

GRANT SELECT, INSERT, UPDATE, DELETE ON timing_task.agent_rag_manifest TO 'petrochat_app'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON timing_task.agent_rag_active TO 'petrochat_app'@'%';
