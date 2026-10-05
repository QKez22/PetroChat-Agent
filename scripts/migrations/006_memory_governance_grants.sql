-- Run as database administrator AFTER the existing memory tables are created.
-- These two legacy application-owned tables lack the agent_ prefix.
-- Local deployment: timing_task / petrochat_app@%. Adjust for other deployments.
-- Do not grant writes to business tables such as affair or affair_task.
USE timing_task;

GRANT SELECT, INSERT, UPDATE, DELETE ON timing_task.user_memory TO 'petrochat_app'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON timing_task.memory_event TO 'petrochat_app'@'%';
