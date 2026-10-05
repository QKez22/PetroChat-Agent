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
