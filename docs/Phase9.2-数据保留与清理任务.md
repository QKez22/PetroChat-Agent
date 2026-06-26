# Phase 9.2 数据保留与清理任务

## 目标

把项目早期规划的数据保留策略落成可执行、可回归、可审计的清理任务。该阶段重点不是“多删数据”，而是让管理员能够先 dry-run 预览影响范围，再显式执行，并在审计日志中留下操作者、时间、范围和原因。

## 默认保留策略

| 数据类型 | 默认保留 | 处理方式 |
| --- | --- | --- |
| 普通会话 | 180 天 | 超期先软删除 `agent_conversation.deleted_at/delete_status` |
| 用户主动删除会话 | 30 天恢复期 | 恢复期后物理删除 `agent_message` 与 `agent_conversation` |
| 工具调用记录 | 365 天 | 删除 `agent_tool_log` 超期记录 |
| RAG 检索上下文 | 90 天 | 如果存在 `agent_retrieval_log` 表，则删除超期记录；当前项目尚未默认建该表 |
| 审计日志 | 1095 天 | 删除 3 年以前 `agent_audit_log`，执行完成后写入新的 `retention_cleanup` 审计 |
| 长期记忆 | 到期时间 | `user_memory.expires_at` 到期后置为 `disabled`，并写入 `memory_event` |

## 环境变量

```env
RETENTION_CONVERSATION_DAYS=180
RETENTION_CONVERSATION_RECOVERY_DAYS=30
RETENTION_TOOL_LOG_DAYS=365
RETENTION_RETRIEVAL_CONTEXT_DAYS=90
RETENTION_AUDIT_LOG_DAYS=1095
RETENTION_TEMP_FILE_DAYS=30
```

Docker Compose 已把这些变量透传给 `api` 容器。

## 命令

默认 dry-run，不修改数据库：

```powershell
uv run python scripts/cleanup_retention.py
```

正式执行：

```powershell
uv run python scripts/cleanup_retention.py --execute --actor-id 1 --reason "monthly retention cleanup"
```

临时覆盖保留周期：

```powershell
uv run python scripts/cleanup_retention.py `
  --conversation-days 180 `
  --conversation-recovery-days 30 `
  --tool-log-days 365 `
  --retrieval-context-days 90 `
  --audit-log-days 1095
```

Docker 演示环境中执行：

```powershell
docker compose run --rm api uv run python scripts/cleanup_retention.py
docker compose run --rm api uv run python scripts/cleanup_retention.py --execute --actor-id 1
```

## 输出示例

```json
{
  "dry_run": true,
  "generated_at": "2026-06-26 10:00:00",
  "cutoffs": {
    "conversation_soft_delete_before": "2025-12-28 10:00:00",
    "conversation_physical_delete_before": "2026-05-27 10:00:00",
    "tool_log_delete_before": "2025-06-26 10:00:00",
    "retrieval_context_delete_before": "2026-03-28 10:00:00",
    "audit_log_delete_before": "2023-06-27 10:00:00"
  },
  "affected": {
    "conversations_soft_deleted": 0,
    "conversations_physical_deleted": 0,
    "messages_physical_deleted": 0,
    "tool_logs_deleted": 0,
    "memories_disabled": 0,
    "audit_logs_deleted": 0
  },
  "skipped": [
    "agent_retrieval_log missing"
  ],
  "audit_log_id": null
}
```

## 审计边界

正式执行时，脚本会在 `agent_audit_log` 写入一条 `retention_cleanup` 记录，`action_detail` 包含：

- `reason`
- `dry_run`
- `cutoffs`
- `affected`
- `skipped`

如果 `agent_audit_log` 表缺失，脚本仍会执行其他清理，但会在输出的 `skipped` 中标记 `agent_audit_log missing for cleanup audit`。

## 后续扩展

- 如果后续落库 RAG 检索上下文，可新增 `agent_retrieval_log` 表，至少包含 `created_at` 与可选 `expires_at`。
- 可以把该脚本接入 Windows 任务计划程序、Linux cron、GitHub Actions self-hosted runner 或 Celery Beat。
- 生产环境建议先连续 dry-run 观察 1-2 个周期，再开启 `--execute`。
