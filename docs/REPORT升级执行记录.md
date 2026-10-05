# 可暂停恢复报表 Agent（2026-10-05）

直接在原 PetroChat-Agent / codex/sql-optimized-chain 实施，按阶段测试、提交、推送。
不修改主聊天图/RAG 行为；用户原有暂存文档不纳入提交。

## 首版范围

- 单任务业务分析：需求/计划 -> 人工确认 -> SQL 查询及快照 -> 图表/分析 -> 草稿确认 -> 导出。
- 下载 ZIP（Markdown、CSV、PNG），不增加 Office/PDF 排版与邮件发送。
- 主动暂停只在安全节点边界生效；断开 SSE 不是取消。未完成外部调用可能重试。
- 查询完成后固定快照；改统计口径产生新修订，下游旧产物失效。
- 任务身份来自登录账号，报告 task_id 与聊天 session_id 分离。
- 固定 workflow_version，仅保证同版本恢复；不自动迁移旧图状态。
- 不使用 pickle，不把 DataFrame/base64 图表塞入 checkpoint，不声称严格 exactly-once。

## 阶段

1. 契约/状态机/原报表基线。
2. 持久化任务、事件、产物与 LangGraph checkpoint/pending-write 存储验证。
3. 报表独立图与数据快照。
4. 人工确认、暂停/恢复/取消与鉴权 API。
5. worker 租约、幂等与崩溃恢复。
6. 前端任务进度/审核/下载。
7. 故障注入验收及真实业务效果报告。

## 阶段 1

新增独立请求、决策、产物引用契约及状态转换约束。未开放路由，未启动后台任务。
基线使用固定部门任务数据验证现有 Markdown 报表、行数与截断提示；既有 render_report 保持不变。
17 项相关测试通过，提交 `2aecab7` 已推送。

## 阶段 2：checkpoint 基础（待 MySQL 迁移验收）

在锁定版本的 BaseCheckpointSaver 协议上实现报表专用同步适配，复用 SQLAlchemy/MySQL，不增加数据库服务。
保存完整小型 checkpoint、父 ID、metadata、pending writes；普通写入去重、错误/中断写入可替换。
运行时不建表，限制单个序列化值 4 MiB、拒绝 pickle；限定普通 channel 的串行报表图，不宣称通用 saver/异步/跨版本迁移兼容。
适配器本身不是鉴权层；后续 API 必须先校验任务归属，再由服务端映射 thread_id。

验证：21 项通过，包含现有报表基线、状态机、文件 SQLite 重建连接、全新 Python 子进程恢复 interrupt、已完成查询不重跑、pending writes、历史列表/筛选与精确线程删除。
测试图的查询是确定性夹具，不是已完成真实报表业务链路；尚未接入线上 API/worker。

管理员下一步执行 `scripts/migrations/007_report_workflow.sql`，一次创建并授权：

- agent_report_task：任务归属、版本、状态、租约；
- agent_report_event：审批与状态审计；
- agent_report_artifact：数据快照/图表/导出文件引用与校验；
- agent_report_checkpoint：图执行状态；
- agent_report_write：节点未完成写入。

2026-10-05 只读预检这五张表均返回 1142（应用账号不可访问，不能据此区分缺表和缺权限）。
只授予这五张表 CRUD，不授予全库、DDL 或业务表写权限。已存在同名表不会被删除/覆盖。
真实 MySQL checkpoint 恢复验证尚未完成，阶段 3–7 尚未执行，不启用报表 Agent 功能。
阶段 2 基础代码合入前：全量 292 项通过，F/I 静态检查通过；3 项既有 jieba 警告。
# 阶段 2 补充：迁移与任务仓储验证（2026-10-06）

- 007 已执行，真实应用账号验证五表读写及 checkpoint/pending writes 往返通过。
- 新增隔离验证脚本 `scripts/verify_report_mysql.py`，只清理本次 UUID，不领取真实任务。
- 任务/审计同事务，乐观 revision，用户隔离，300 秒租约，最多 3 次失败尝试；检查点写入同事务校验租约，阻止旧 worker 覆盖。
- `tests/test_report_store.py` + persistence：7 passed。尚未启用业务工作流。

## 阶段 3：可恢复业务图（2026-10-06）

- 方案确认 → 只读 NL2SQL 固定快照 → 图表/描述性概览 → 草稿确认 → ZIP（Markdown、CSV、PNG、溯源 JSON）。方案是明确需求/执行策略，不声称提供 SQL 预审批。
- 每个节点同步持久化后返回调度层；快照/草稿/导出放在持久卷，checkpoint 只保存引用。产物 SHA256 校验、原子发布、清单写入租约 fencing；CSV 防公式注入。
- 修改需求新建 generation，必须再次审批，不复用旧快照。批准绑定 interrupt ID，避免过时确认落到另一道门禁。
- 三项工作流测试通过：双门禁/暂停恢复/导出、修改口径、快照落盘后崩溃恢复不重复查询。此时尚未接 API 和前端。

## 阶段 4–5：授权 API 与托管 worker（2026-10-06）

- `/api/reports`：创建/列表/详情/actions/events/artifacts。身份仅取 JWT；跨用户返回 404，重复/过时操作 409，禁用时 503。产物下载校验哈希，未完成不暴露 ZIP。
- FastAPI 生命周期启动独立线程，串行执行，每节点重新领取租约；多 worker 依赖 MySQL 8 行锁/skip locked 和写入 fencing。无 Redis/Celery。
- `REPORT_ENABLED` 默认 false，迁移后开启；所有实例必须共享持久产物目录。Docker 复用挂载 `/app/data`。
- 故障测试覆盖取消执行中任务、审批 checkpoint 落盘后进程退出（不能误批准草稿）、产物损坏、worker 启停。关闭浏览器不取消任务。
