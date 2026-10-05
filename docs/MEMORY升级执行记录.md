# 长期记忆升级（2026-10-05）

在原 PetroChat-Agent / codex/sql-optimized-chain 分支逐阶段修改、测试、提交和推送。
用户已有暂存文档不纳入提交。不迁移框架，不删除业务数据。

## 阶段与验收

1. 冻结开发者编写的去重安全用例，记录旧实现基线。小样本只作回归，不作为生产准确率。
2. 用户隔离的批量校验、实时过期控制、保守去重，测试 SQL 次数和危险变更。
3. 幂等同步、持久重试、分页对账与故障测试。新增表需要部署迁移和应用权限。
4. 结构化偏好版本及有界语义缓存，保留离线词法降级；不以 embedding 阈值自动覆盖冲突。
5. 在固定数据与相同条件下比较组件方案，记录性能/质量边界，决定是否减组件。

## 基线口径

`uv run python scripts/benchmark_memory.py`：8 对固定文本，包括数字、否定、项目、单位变化和同义表达。
旧实现为精确匹配加 SequenceMatcher：8 对中正确 2 对，4 次危险误合并，2 次同义漏合并。
阶段 1：原有记忆测试和基线数据检查共 12 项通过。此阶段不改变业务行为。
延迟必须区分本地计算与真实外部服务；不得用单元测试时间冒充线上性能。

## 阶段 2：正确性

- 单次用户隔离批量 SELECT 校验候选；空 ID 列表不查库，非法 ID 忽略。
- 召回与索引构建实时排除过期项，支持 ISO 时间转 UTC、更新/清除有效期。
- 暂停危险模糊去重，保留空白归一后的精确判定；同义漏合并暂不以误合并换取。
- fallback 合并不再直接比较不同来源的分数。
- 31 项记忆/保留策略/API 测试通过。固定 8 对中正确 6 对、危险误合并 0、同义漏合并 2。
- 数据库批量校验测试确认一次 SELECT；未测线上延迟百分比。

## 阶段 3：同步可靠性（代码就绪，真实部署待迁移）

- `MEMORY_SYNC_ENABLED=false` 默认保持兼容。打开后记忆变更与 outbox 同事务提交，缺表会回滚业务写入，不静默丢任务。
- 同记忆任务合并，持久退避重试（上限 300 秒）、120 秒租约、最新状态读取、更新代次检查。
- MySQL 全量 keyset 分页对账；仅清理具有明确用户/业务记忆 ID 的派生索引。
- 确定性索引 ID + upsert；内容指纹阻止主召回使用旧索引选择新正文。
- Mem0 仍用于抽取和搜索；派生索引直接写其 Chroma collection，避免无意义的推理和重复 history 记录。
- 旧重建脚本不再清空索引，也不再把吞掉的异常计作成功。
- 注意：这是至少一次同步与最终一致，不是跨库事务。超出租约的旧 worker 可能产生短暂旧向量，读门禁拒绝，下一次对账修复。
- 单元测试覆盖失败重试、退避、进程租约恢复、事务回滚、处理中更新、分页、孤儿与重复记录修复、upsert 幂等。
- 本阶段连同记忆、API、retention、Agent runtime、上下文治理共 63 项测试通过；MySQL/Chroma 真实联调尚未通过，等待管理员迁移。

部署顺序：

1. 管理员执行 `scripts/migrations/005_memory_sync.sql`（本机 timing_task / petrochat_app@%）。
2. 应用账号验证 SELECT/INSERT/UPDATE/DELETE，然后进行真实 MySQL + 独立测试 Chroma collection 验收。
3. 验证后才开启 `MEMORY_SYNC_ENABLED=true`，同时保持 `MEM0_ENABLED=true`。
4. 启动受进程管理器托管的 `uv run python scripts/sync_memory_index.py --watch`；每 5 秒消费、每 300 秒对账，故障记录错误类型，监控 pending 最老时间、attempts 和失败计数。
5. 回滚开关前先停止 worker；不要删除 MySQL 真相源，也不要清空索引。

2026-10-05 只读预检：新表不存在、应用账号无 CREATE 权限。未尝试提权或改用业务账号。
阶段 4/5（结构化版本、语义缓存、组件实测比较）尚未执行，不把安全回归结果当作语义优化收益。

## 迁移后权限复核

管理员执行 005 后，应用账号 `petrochat_app@%` 对 `agent_memory_sync` 的 SELECT/UPDATE/DELETE 空操作检查通过。
但旧应用表 `user_memory`、`memory_event` 的 SELECT/UPDATE/DELETE 均返回 MySQL 1142（权限不足）。
因此真实记忆写入、事务 outbox、MySQL/Chroma 联调仍被阻塞；未开启新同步功能，也未操作业务数据。
补充 `006_memory_governance_grants.sql`，只授权上述两张旧应用记忆表的 CRUD，不授予全库或业务表写权限。
执行后继续验证实际 INSERT/事务回滚和隔离数据同步，再进入阶段 4/5。

006 执行后复核通过：三表 SELECT/UPDATE/DELETE 授权有效；`check_memory_live.py --execute`
在真实 MySQL、独立随机租户与 Chroma 测试集合上验证创建（INSERT）、更新、幂等重复执行、
真实 embedding/搜索、丢失索引对账修复、删除全部通过。仅删除本次测试记录和测试集合。
同步 worker 增加可选 user_id 限定，隔离测试不消费任何现有用户任务。
测试脚本适配 Chroma 0.6 集合名称返回类型，并在 Windows 清理前关闭 Mem0 SQLite history。

## 阶段 4a：轻量版本管理

- 使用既有 user_memory metadata_json 保存 scope/key/value/unit/revision/valid_from，事件保存 before/after（旧快照附 valid_to），无需新表。
- `PUT /api/memory/preferences` 只修改登录用户的偏好；创建 expected_revision=0，更新需当前版本，冲突 HTTP 409。
- 用户+作用域+键的确定性主键、MySQL 行锁与 revision 条件更新防止丢失更新；通用 PATCH 禁止绕过结构化版本接口。
- 已删除/禁用的结构化偏好不允许自动复活；相同值不重复写事件。
- 明确单句的默认吨位、回答详略可自动写入；项目/否定/多条件等歧义表达不自动覆盖，显式 API 可指定 scope。
- 不把助手生成内容送作偏好抽取依据；普通新建/更新事件开始保存正文快照，过去缺失的历史无法补造。
- 38 项相关测试通过，真实 MySQL revision 更新/旧版本拒绝及 Chroma 同步通过。
- 这是当前值+版本审计，不是完整双时态模型；也不声称覆盖所有自然语言偏好。
