# Phase 11 上下文与长期记忆流程

本文记录当前 PetroChat-Agent 的上下文体系改造，重点解决三个问题：

1. 会话变长后不能把所有历史消息无限塞进 prompt。
2. 最近窗口之外的关键信息不能丢。
3. Mem0 自动抽取不能直接污染正式长期记忆召回。

## 1. 总体架构

```text
用户问题
  ↓
当前输入
  ↓
会话滚动摘要 agent_conversation_summary
  ↓
最近 N 轮短期消息 agent_message
  ↓
长期记忆召回 user_memory + Mem0 active collection
  ↓
RAG / NL2SQL / Tool Calling / General Agent
```

上下文分层如下：

| 层级 | 存储 | 作用 | 是否跨会话 |
| --- | --- | --- | --- |
| 当前问题 | 请求体 | 本轮用户输入 | 否 |
| 短期上下文 | `agent_message` 最近 `SHORT_TERM_TURNS` 轮 | 保留最近多轮指代、追问、约束 | 否 |
| 会话滚动摘要 | `agent_conversation_summary` | 压缩更早消息，避免 6 轮之外关键信息丢失 | 否 |
| 长期记忆主库 | `user_memory` | 用户偏好、项目偏好、历史决策、稳定业务条件 | 是 |
| 记忆审计 | `memory_event` | 记录创建、更新、禁用、删除、同步事件 | 是 |
| 候选记忆索引 | Mem0 `petrochat_memory_candidates` | 只给自动抽取候选使用 | 是 |
| 正式记忆索引 | Mem0 `petrochat_memories` | 只同步 MySQL 中已审核 active 记忆 | 是 |
| 规范知识库 | Chroma `petrochat_specs` | 石化制度/规范 RAG | 否，按知识库版本管理 |

## 2. 短期窗口与滚动摘要

当前实现不是只保留最近 6 轮然后丢弃后面的内容，而是：

1. 原始消息继续写入 `agent_message`。
2. prompt 中只注入最近 `SHORT_TERM_TURNS` 轮原文消息。
3. 更早且尚未摘要的消息进入候选摘要区，并按批量触发策略压缩成 `agent_conversation_summary.summary_text`。
4. 下次对话构建 Agent state 时，摘要作为 system message 注入在长期记忆之后、最近历史之前。

这样既控制 token，又能保留“本轮会话已经确认过什么、还有什么没完成、前面做过哪些查询”。

### 2.1 裁剪策略

| 项 | 当前策略 |
| --- | --- |
| 原始消息 | 不因裁剪而删除，仍在 `agent_message` |
| 最近窗口 | `SHORT_TERM_TURNS * 2` 条消息，按 user/assistant 成对计算 |
| 摘要指针 | `summarized_until_message_id` 表示当前摘要已经覆盖到哪条消息 |
| 候选摘要区 | `summarized_until_message_id` 之后、最近窗口之前的消息 |
| 摘要触发 | 超窗是前置条件，再由批量大小、token 预算、长工具结果、主题切换等条件触发 |
| 摘要长度 | `CONVERSATION_SUMMARY_MAX_TOKENS` 和 `CONVERSATION_SUMMARY_MAX_CHARS` 双重控制 |
| 摘要失败 | 记录 warning，继续用最近窗口回答 |

### 2.2 摘要触发条件

系统不是每次多一条旧消息就摘要，而是“摘要指针 + 批量触发”：

```text
m1, m2, m3, ... m20
最近窗口：最后 SHORT_TERM_TURNS * 2 条
候选摘要区：summarized_until_message_id 之后、最近窗口之前的消息
```

满足“已经超过最近窗口”后，以下任一条件成立才刷新摘要：

| 条件 | 配置 |
| --- | --- |
| 待摘要消息达到批量阈值 | `CONVERSATION_SUMMARY_MIN_PENDING_MESSAGES` |
| 距离上次摘要超过一定轮数 | `CONVERSATION_SUMMARY_TRIGGER_TURNS` |
| 当前会话估算 token 接近输入预算 | `CONVERSATION_SUMMARY_TRIGGER_TOKEN_RATIO` |
| 候选区出现长工具结果、代码块、长 SQL 或 Traceback | `CONVERSATION_SUMMARY_LONG_MESSAGE_TOKENS` |
| 用户明显切换主题 | 规则检测，后续可替换为 LLM 判定 |

### 2.3 摘要内容结构

滚动摘要按固定栏目组织，便于 Agent 后续继承上下文：

```text
【会话摘要】
已确认事实：最多 5 条
当前任务目标：最多 3 条
用户偏好：最多 3 条
未解决问题：最多 3 条
```

摘要只用于当前 `conversation_id`，不会进入长期用户记忆，也不会跨用户复用。

### 2.4 三层剪枝

| 剪枝层 | 策略 |
| --- | --- |
| 原文消息剪枝 | 最近 `SHORT_TERM_TURNS` 轮完整保留，更早消息不直接进 prompt |
| 摘要剪枝 | 摘要按固定结构和 `CONVERSATION_SUMMARY_MAX_TOKENS` 再压缩 |
| 长期记忆剪枝 | Mem0/MySQL 召回 top_k，经状态、权限、相关性过滤后只注入少量 active 记忆 |

数据库存储和模型上下文是两件事：MySQL 保存完整历史用于审计、回放和用户查看；prompt 只放当前问题、最近窗口、摘要、少量长期记忆和少量 RAG 证据。

## 3. 长期记忆写入流程

长期记忆采用“Mem0 自动抽取 + MySQL 主存储 + Mem0 正式语义索引”的流程。

```text
用户对话
  ↓
MemoryTrigger 判断是否值得抽取
  ↓
Mem0.add(messages, infer=True, metadata={"stage": "candidate"})
  ↓
候选记忆进入 petrochat_memory_candidates
  ↓
MemoryPolicy 过滤敏感信息、重复信息、低价值信息
  ↓
写入 MySQL user_memory
  ↓
记录 memory_event
  ↓
同步 active memory 到 Mem0 正式 collection petrochat_memories
```

关键约束：

- Mem0 候选 collection 只负责抽取候选，不参与正式召回。
- `user_memory` 是长期记忆事实主库，负责状态、权限、删除、审计。
- 只有 MySQL 中 `status=active` 的记忆才会同步到正式 collection。
- `disabled` / `deleted` 记忆永远不能注入 prompt。

## 4. 长期记忆召回流程

```text
用户问题
  ↓
判断是否需要长期记忆
  ↓
搜索 Mem0 active collection petrochat_memories
  ↓
拿 memory_id 回 MySQL 校验状态、用户、类型和权限
  ↓
合并 MySQL 规则召回结果
  ↓
去重、排序、过滤
  ↓
注入 prompt
```

召回来源需要保留标记：

```json
{
  "memory_id": "12",
  "content": "...",
  "source": "mysql",
  "score": null
}
```

```json
{
  "memory_id": "12",
  "content": "...",
  "source": "mem0",
  "score": 0.82
}
```

合并规则：

- 同 `memory_id`：MySQL 版本优先。
- 不同 `memory_id`：按 `score`、`updated_at` 和类型权重排序。
- `disabled` / `deleted`：永远过滤。
- Mem0 不可用：自动降级到 MySQL 关键词/规则召回。

## 5. 哪些对话需要长期记忆

| 场景 | 策略 |
| --- | --- |
| 普通知识问答 | RAG 为主，长期记忆少查或不查 |
| 多轮上下文问题 | 优先查 session memory 和滚动摘要 |
| 用户偏好/项目偏好/历史决策 | 查 user memory |
| 管理员查看评估/Trace | 一般不查用户长期记忆 |
| NL2SQL | 只查用户历史偏好、默认筛选条件，不查业务文档记忆 |
| 权限/安全/账号问题 | 不写长期记忆，必要时只记录审计 |

## 6. 冲突与过滤

长期记忆写入前必须经过 `MemoryPolicy`：

| 类型 | 处理 |
| --- | --- |
| 敏感信息 | 不写入长期记忆 |
| 低价值寒暄 | 不写入长期记忆 |
| 临时问题 | 不写入长期记忆 |
| 与已有记忆重复 | 合并或跳过 |
| 与已有记忆冲突 | 标记冲突，优先保留更新时间更新、置信度更高、来源更明确的记忆 |
| 用户显式纠错 | 旧记忆禁用，新记忆 active，并写 `memory_event` |

RAG 文档事实与用户记忆必须分离：规范制度进入 RAG collection，用户偏好和项目上下文进入记忆体系。

## 7. 新增表 SQL

需要新建会话滚动摘要表：

```sql
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
```

仓库中也提供了完整 SQL 文件：

```text
docs/sql/phase11_context_summary_tables.sql
```

如果已经按旧版 SQL 创建了 `covered_message_id`，执行迁移脚本即可：

```text
docs/sql/phase11_context_summary_migration.sql
```

Docker demo 初始化脚本 `docker/mysql/init/001_demo_schema.sql` 已同步包含该表。

## 8. 配置项

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `SHORT_TERM_TURNS` | 6 | prompt 中保留最近多少轮原文消息 |
| `CONVERSATION_SUMMARY_ENABLED` | true | 是否启用会话滚动摘要 |
| `CONVERSATION_SUMMARY_TRIGGER_TURNS` | 6 | 超过多少轮后刷新摘要 |
| `CONVERSATION_SUMMARY_MAX_CHARS` | 1600 | 摘要最大字符数 |
| `CONVERSATION_SUMMARY_MAX_TOKENS` | 1000 | 摘要最大估算 token |
| `CONVERSATION_SUMMARY_MIN_PENDING_MESSAGES` | 4 | 待摘要消息达到多少条才批量刷新 |
| `CONVERSATION_SUMMARY_TRIGGER_TOKEN_RATIO` | 0.75 | 会话估算 token 达到输入预算多少比例时触发摘要 |
| `CONVERSATION_SUMMARY_LONG_MESSAGE_TOKENS` | 800 | 单条消息超过多少估算 token 视为长工具/代码结果 |
| `CONTEXT_WINDOW_TOKENS` | 32000 | 当前模型最大上下文窗口估算 |
| `CONTEXT_OUTPUT_TOKEN_RESERVE` | 4000 | 给模型输出预留 token |
| `CONTEXT_INPUT_TOKEN_BUDGET` | 12000 | PetroChat 单次请求输入上下文预算 |
| `CONTEXT_SYSTEM_TOKEN_BUDGET` | 2000 | 系统提示词和路由提示词预算 |
| `LONG_TERM_MEMORY_LIMIT` | 5 | 长期记忆召回数量 |
| `MEM0_CANDIDATE_COLLECTION` | `petrochat_memory_candidates` | Mem0 候选抽取 collection |
| `MEM0_ACTIVE_COLLECTION` | `petrochat_memories` | Mem0 正式召回 collection |

## 9. Prompt 组装预算

每次请求按以下顺序组装 prompt：

```text
1. 当前问题
2. 最近 N 轮原文
3. session_summary
4. 判断是否需要长期记忆
5. 检索长期记忆 top_k
6. 检索 RAG 文档 top_k
7. 加载工具结果摘要
8. 按 token budget 组装 prompt
9. 超出预算则裁剪
```

预算分两层：

| 层 | 说明 |
| --- | --- |
| 模型上下文窗口 | 例如 32k，但不能全部用满，需要预留输出 |
| 应用层输入预算 | PetroChat 默认只使用 12k 输入上下文，降低成本、延迟和噪声 |

示例：

```text
模型窗口：32k
预留输出：4k
系统提示词预算：2k
应用层输入预算：12k
```

## 10. 当前实现边界

- 已实现会话滚动摘要表、读写、刷新和 Agent state 注入。
- 已实现摘要指针、批量触发、估算 token 预算和 prompt 注入前裁剪。
- 已实现 Mem0 候选/正式 collection 隔离、MySQL 回表校验和失败降级。
- 已在非流式响应和 SSE meta 中补充记忆召回摘要字段。
- 摘要生成当前是规则压缩版，后续可替换为 LLM summarizer，但仍应写入同一张主表。
- Redis 适合后续做 session 热缓存和分布式锁，不建议替代 MySQL 主存储。
