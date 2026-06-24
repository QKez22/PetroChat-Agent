# PetroChat-Agent v1.1+ 记忆、评估与前端规划

> 本文是《PetroChat-Agent 项目结构说明书-Python版》的补充规划，面向 v1.0-multiagent 之后的演进。目标不是堆功能，而是把项目升级成一个可以在简历和面试中讲清楚闭环的 LLM 应用工程：有 Agent 编排、有记忆、有可量化评估、有前端观测和运维视角。

## 1. 当前基线

### 1.1 已完成能力

| 阶段 | 能力 | 当前状态 |
| --- | --- | --- |
| Phase 1 | RAG 问答 | 规范文档解析、Chroma 检索、FastAPI SSE、LangSmith 链路 |
| Phase 2 | Tool Calling | 单位换算、条款查询、文档内检索、RAG-as-tool |
| Phase 3 | MCP Server | FastMCP 暴露工具，stdio + streamable-http，MCP 开关 |
| Phase 4 | 多 Agent 数据问答 | Supervisor 路由到 QA / SQL / General，NL2SQL，报表图侧信道 |
| Frontend v0 | Vue3 工作台 | 对话、Markdown、SSE、图表、管理员本地观测台 |

### 1.2 当前短板

当前项目已经能演示“问答 + 工具 + 数据查询”，但如果要作为简历项目深入讲，需要补齐四个工程闭环：

1. 记忆闭环：多轮对话不能只依赖 LangGraph 当前 messages，需要短期记忆、摘要记忆、长期记忆和召回策略。
2. 评估闭环：RAG、NL2SQL、Memory 不能只靠人工感觉，需要可复现指标，如 Recall@K、MRR、执行准确率、记忆命中率。
3. 前端闭环：前端不仅是聊天窗口，还要能展示 Agent 过程、会话历史、管理员观测和评估结果。
4. 产品闭环：每一阶段都要有可演示入口、可测试脚本、README 说明和面试讲法。

## 2. 目标架构

### 2.1 v1.1+ 分层

```text
PetroChat-Agent
├── frontend/                         # Vue3 前端
│   ├── Chat Workspace                 # 用户对话、SSE、Markdown、图表
│   ├── Admin Console                  # 会话观测、路由、工具、错误、导出
│   └── Evaluation Dashboard           # 指标看板、样例回放、失败分析
├── FastAPI
│   ├── chat routes                    # /api/chat, /api/chat/stream
│   ├── session routes                 # 会话、消息、历史记录
│   ├── memory routes                  # 记忆查询、写入、审核、删除
│   └── eval routes                    # 评估集运行与指标读取
├── LangGraph Supervisor
│   ├── supervisor                     # 意图识别和路由
│   ├── memory_load                    # 短期/长期记忆加载
│   ├── qa                             # RAG 规范问答
│   ├── sql                            # NL2SQL + 报表
│   ├── general                        # ReAct 工具循环
│   └── memory_write                   # 对话结束后的记忆沉淀
├── Retrieval
│   ├── spec retriever                 # 规范知识库召回
│   ├── memory retriever               # 长期记忆召回
│   └── rerank / MMR                   # 重排与去冗余
├── Persistence
│   ├── MySQL                          # 会话、消息、评估结果、业务表
│   └── Chroma / PGVector              # 规范向量、长期记忆向量
└── Evaluation
    ├── rag_eval                       # Recall@K、MRR、答案忠实性
    ├── sql_eval                       # SQL 有效率、执行准确率、安全违规率
    ├── memory_eval                    # 记忆命中、冲突、过期、有效性
    └── frontend_eval                  # SSE 稳定性、错误展示、交互闭环
```

### 2.2 设计原则

| 原则 | 说明 |
| --- | --- |
| 记忆可解释 | 每条长期记忆必须有来源、时间、置信度、类型和可删除入口 |
| 召回可度量 | 检索不是“感觉相关”，而是要能跑 Recall@K / MRR / nDCG |
| 写入要克制 | 不把每一句话都写入长期记忆，只沉淀稳定偏好、业务背景、明确结论 |
| 文档与会话分离 | 规范文档引用和用户记忆引用分开展示，避免把私人记忆伪装成规范依据 |
| 前端可观测 | 用户能看答案，管理员能看过程，开发者能看指标和失败样例 |
| 渐进实现 | 先本地会话持久化，再短期窗口，再长期记忆，再评估看板 |

## 3. Memory 体系规划

### 3.1 记忆分层

| 层级 | 生命周期 | 存储位置 | 作用 | 示例 |
| --- | --- | --- | --- | --- |
| Working Context | 单次请求 | LangGraph `AgentState` | 当前问题、路由、工具结果 | 当前用户问“统计仪表专业事务” |
| Short-term Memory | 当前会话 | messages 滑动窗口 + session store | 多轮上下文衔接 | “上一个问题里的仪表专业” |
| Summary Memory | 当前会话长期摘要 | MySQL `conversation_summary` | 压缩旧对话，控制 token | “本轮会话主要围绕运行中事务统计” |
| Long-term Memory | 跨会话 | MySQL + 向量库 | 用户偏好、业务背景、历史决策 | “用户关注仪表专业、偏好 Markdown 表格” |
| Domain Knowledge | 长期稳定 | Chroma / PGVector | 石化规范知识库 | ITPM 条款、设备分级标准 |

### 3.2 短期记忆：滑动窗口

#### 目标

控制上下文长度，同时保留最近多轮对话的语义连续性，解决“多轮追问”和“指代消解”。

#### 实现思路

新增 `memory` 包：

```text
src/petrochat/app/memory/
├── __init__.py
├── short_term.py       # 滑动窗口、token 预算、消息裁剪
├── summarizer.py       # 会话摘要生成与更新
├── long_term.py        # 长期记忆抽取、写入、召回
├── schema.py           # Pydantic 实体
└── store.py            # MySQL / Chroma 存储适配
```

扩展 `AgentState`：

```python
class AgentState(TypedDict, total=False):
    question: str
    session_id: str
    user_id: str
    messages: Annotated[list[BaseMessage], add_messages]
    short_term_messages: list[dict[str, Any]]
    conversation_summary: str
    recalled_memories: list[dict[str, Any]]
    memory_trace: list[dict[str, Any]]
    retrieved: list[dict[str, Any]]
    answer: str
    citations: list[str]
    next: NextNode
```

#### 滑动窗口策略

| 项 | 策略 |
| --- | --- |
| 窗口单位 | 最近 N 轮 user/assistant 消息，而不是单条 message |
| 默认窗口 | 最近 6 轮，后续按 token 预算动态裁剪 |
| Token 预算 | 记忆上下文不超过总 prompt 的 25%-35% |
| 超窗处理 | 旧轮次进入 `conversation_summary`，不直接丢弃 |
| 工具结果 | 只保留工具名、关键参数、摘要，不保留完整大表 |
| 报表图片 | 不进入 LLM 上下文，只在前端和 meta 中展示 |

#### 节点位置

```text
START
  -> memory_load
  -> supervisor
  -> qa / sql / general
  -> memory_write
  -> END
```

`memory_load` 负责把短期窗口、摘要和长期记忆打包进 state；`memory_write` 负责在答案生成后判断是否沉淀新记忆。

### 3.3 长期记忆

#### 记忆类型

| 类型 | 内容 | 是否向量化 | 写入条件 |
| --- | --- | --- | --- |
| user_preference | 用户偏好 | 是 | 用户明确表达或多次稳定出现 |
| domain_focus | 用户关注领域 | 是 | 会话中持续关注某专业/设备/业务 |
| project_context | 项目上下文 | 是 | 用户明确说明项目目标、约束、计划 |
| decision | 已达成决策 | 是 | 出现“就按这个做”“确定采用” |
| correction | 用户纠错 | 是 | 用户纠正 Agent 术语、口径、事实 |
| unsafe_or_sensitive | 敏感内容标记 | 否或脱敏 | 仅记录风险，不写原文 |

#### 建议 MySQL 表

```sql
CREATE TABLE conversation (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    title VARCHAR(255),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE message (
    id VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL,
    role VARCHAR(32) NOT NULL,
    content MEDIUMTEXT NOT NULL,
    route VARCHAR(32),
    latency_ms INT,
    created_at DATETIME NOT NULL
);

CREATE TABLE memory_item (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    memory_type VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    source_message_id VARCHAR(64),
    confidence DECIMAL(4,3) NOT NULL DEFAULT 0.800,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    expires_at DATETIME NULL
);

CREATE TABLE memory_event (
    id VARCHAR(64) PRIMARY KEY,
    memory_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    detail TEXT,
    created_at DATETIME NOT NULL
);
```

向量库中保存 `memory_item.id`、`user_id`、`memory_type`、`content`、`created_at` 等元数据，正文仍以 MySQL 为准。

#### 写入策略

1. 对话结束后运行 `memory_write`。
2. 用轻量 LLM 或规则抽取候选记忆。
3. 候选记忆必须满足：
   - 对未来回答有用；
   - 不是临时情绪或一次性指令；
   - 不包含敏感隐私原文；
   - 与已有记忆不冲突，或能形成更新事件。
4. 写入前做去重：
   - exact hash 去重；
   - embedding 相似度去重；
   - 同类型同主题记忆合并。
5. 写入后记录 `memory_event`，方便管理员审计。

#### 召回策略

长期记忆召回不能替代规范知识库，只能作为用户上下文增强。

```text
用户问题
  -> query rewrite
  -> 召回最近短期窗口
  -> 召回 conversation_summary
  -> 向量召回 long-term memory Top-K
  -> RAG 召回 domain knowledge Top-K
  -> MMR / rerank 去冗余
  -> prompt context pack
```

上下文打包顺序：

1. 系统角色与安全边界；
2. 当前用户问题；
3. 会话摘要；
4. 最近 N 轮短期窗口；
5. 与当前问题相关的长期记忆；
6. 规范知识库检索结果；
7. 工具可用性说明。

### 3.4 记忆安全与可控性

| 风险 | 控制策略 |
| --- | --- |
| 记错用户偏好 | 记忆有置信度和来源，管理员可删除 |
| 敏感信息沉淀 | 默认不写手机号、账号、密钥、身份证等敏感内容 |
| 旧记忆污染 | `expires_at`、status、memory_event 支持过期和撤销 |
| 规范依据混淆 | 前端区分“规范引用”和“记忆引用” |
| 多用户串记忆 | 所有记忆按 `user_id` 隔离，后续可扩展 tenant_id |

## 4. Evaluation 指标体系

### 4.1 总体原则

评估不是单次 demo，而是可反复运行的回归系统。每次改动 RAG、SQL、Memory、Prompt 或前端 SSE，都能回答三个问题：

1. 有没有变准？
2. 有没有变慢？
3. 有没有引入安全或稳定性回归？

### 4.2 RAG 评估

#### 数据集

```text
data/eval/
├── rag_questions.yaml       # 规范问答样例
├── rag_labels.yaml          # 标注相关 chunk / section
├── sql_questions.yaml       # NL2SQL 样例
├── memory_questions.yaml    # 多轮记忆样例
└── golden_answers.yaml      # 参考答案与评分规则
```

#### 检索指标

| 指标 | 含义 | 目标 |
| --- | --- | --- |
| Recall@K | 正确 chunk 是否在 Top-K 中 | Recall@5 >= 0.85 |
| MRR | 第一个正确 chunk 的排名质量 | MRR >= 0.65 |
| nDCG@K | 多个相关 chunk 的排序质量 | nDCG@5 >= 0.75 |
| Context Precision | 召回上下文中有效信息比例 | >= 0.70 |
| Citation Coverage | 答案引用是否覆盖关键依据 | >= 0.80 |

#### 生成指标

| 指标 | 含义 | 目标 |
| --- | --- | --- |
| Faithfulness | 答案是否由上下文支持 | >= 4/5 |
| Answer Relevance | 是否回答用户问题 | >= 4/5 |
| Citation Correctness | 引用编号是否真实对应 | >= 0.90 |
| Hallucination Rate | 无依据编造比例 | <= 0.05 |

### 4.3 NL2SQL 评估

| 指标 | 含义 | 目标 |
| --- | --- | --- |
| SQL Valid Rate | 生成 SQL 能通过 sqlglot 校验 | >= 0.95 |
| Execution Accuracy | 执行结果符合 golden 结果 | >= 0.85 |
| Read-only Violation | 写操作/系统库访问违规率 | 0 |
| Timeout Rate | 超时比例 | <= 0.05 |
| Business Term Accuracy | “事务/任务”等业务语义识别准确率 | >= 0.90 |
| Report Render Rate | 可报表数据成功生成 Markdown/图表 | >= 0.90 |

### 4.4 Memory 评估

| 指标 | 含义 | 目标 |
| --- | --- | --- |
| Memory Hit Rate | 需要记忆的问题是否召回正确记忆 | >= 0.80 |
| Memory Precision | 召回记忆是否真的相关 | >= 0.75 |
| Contradiction Rate | 新旧记忆冲突未处理比例 | <= 0.05 |
| Stale Memory Rate | 过期记忆仍影响回答的比例 | <= 0.05 |
| Write Precision | 写入长期记忆中真正有价值的比例 | >= 0.80 |
| User Control Coverage | 可查看、删除、导出的记忆比例 | 100% |

### 4.5 前端与系统指标

| 指标 | 含义 | 目标 |
| --- | --- | --- |
| SSE First Token Latency | 用户发送到首 token 时间 | P50 < 3s |
| Full Answer Latency | 完整回答耗时 | P50 < 15s |
| Stream Error Visibility | 流式错误是否在 UI 明确展示 | 100% |
| Admin Trace Completeness | 管理员页是否记录路由、耗时、工具、引用 | 100% |
| Chart Render Success | `meta.chart_data_uri` 是否正常展示 | >= 0.95 |
| Frontend Build Stability | `pnpm build` 是否通过 | 100% |

### 4.6 评估实现步骤

```text
Step E1: 建立 data/eval 样例集
Step E2: 编写 scripts/eval_rag.py，输出 retrieval metrics
Step E3: 编写 scripts/eval_sql.py，输出 SQL execution metrics
Step E4: 编写 scripts/eval_memory.py，模拟多轮会话并验证记忆召回
Step E5: 把评估结果保存到 data/eval/results/*.json
Step E6: 前端管理员页增加 Evaluation Dashboard
Step E7: README 展示关键指标和失败案例分析
```

## 5. 前端规划

### 5.1 当前前端基线

| 功能 | 当前状态 |
| --- | --- |
| 对话输入 | 已完成 |
| POST SSE 消费 | 已完成 |
| Markdown 渲染 | 已完成 |
| 图表 data URI 展示 | 已完成 |
| 引用展示 | 已完成 |
| 管理员本地观测 | 已完成 |
| 会话持久化 | 浏览器 localStorage 临时版 |

### 5.2 前端信息架构

```text
Vue3 Frontend
├── Chat
│   ├── 对话流
│   ├── 工具事件时间线
│   ├── 引用与图表
│   └── 错误与重试
├── Sessions
│   ├── 会话列表
│   ├── 历史搜索
│   ├── 会话标题
│   └── 导出 Markdown / JSON
├── Admin
│   ├── 会话观测
│   ├── 路由分布
│   ├── 工具调用统计
│   ├── 错误聚合
│   └── LangSmith trace 链接
├── Memory
│   ├── 用户记忆列表
│   ├── 记忆来源
│   ├── 启用/禁用/删除
│   └── 记忆召回解释
└── Evaluation
    ├── RAG 指标
    ├── SQL 指标
    ├── Memory 指标
    └── 失败样例回放
```

### 5.3 页面分期

#### Frontend Phase F1：稳定对话台

目标：让前端成为后端能力的稳定演示入口。

任务：

1. 固定 Vite 代理到 `127.0.0.1:8000`，规避 Windows `localhost -> ::1` 问题。
2. 明确 API 在线状态。
3. 对 `token/tool_call/tool_result/meta/error/done` 全事件做 UI 呈现。
4. SQL 分支如果 SSE 无 token，自动 fallback 到 `/api/chat`。
5. 失败时展示错误类型和重试入口。

验收：

```text
pnpm build 通过
/health 可用时状态为在线
/api/chat/stream 可完成一轮问答
图表 meta 能正常展示
```

#### Frontend Phase F2：会话系统

目标：让用户可以回看历史，而不是每次刷新都丢上下文。

任务：

1. 后端新增 conversation/message API。
2. 前端左侧增加会话列表。
3. 支持新建、重命名、删除、搜索会话。
4. 支持导出会话 Markdown。
5. 消息中保存 route、latency、citations、chart meta。

验收：

```text
刷新页面后历史会话仍在
多轮会话能恢复上下文
管理员能看到每轮路由和耗时
```

#### Frontend Phase F3：管理员观测台

目标：让面试时能展示“我不仅会做聊天框，还会做 Agent 可观测性”。

任务：

1. 从 localStorage 观测升级为后端持久化观测。
2. 展示路由分布：QA / SQL / General。
3. 展示工具调用统计。
4. 展示错误列表和失败请求详情。
5. 展示 LangSmith trace 链接或 run id。

验收：

```text
能定位一次失败问答在哪个节点失败
能展示某天 SQL 查询成功率和平均耗时
能导出管理员审计 JSON
```

#### Frontend Phase F4：记忆管理

目标：让长期记忆透明、可控、可解释。

任务：

1. 用户可查看长期记忆。
2. 每条记忆显示来源消息、创建时间、类型、置信度。
3. 支持禁用、删除、导出。
4. 在回答详情中展示“本次使用了哪些记忆”。
5. 管理员能看到记忆写入/更新事件。

验收：

```text
用户能删除一条错误记忆
删除后同类问题不再召回该记忆
回答中记忆引用和规范引用分开
```

#### Frontend Phase F5：评估看板

目标：把项目质量指标可视化。

任务：

1. 读取 `data/eval/results/*.json` 或后端 eval API。
2. 展示 RAG Recall@K、MRR、Faithfulness。
3. 展示 NL2SQL 执行准确率、安全违规率。
4. 展示 Memory hit rate、contradiction rate。
5. 支持失败样例回放：输入、召回、答案、指标、trace。

验收：

```text
一次评估运行后前端能看到指标变化
能点开失败样例分析原因
README 能贴指标截图作为简历材料
```

## 6. 后端阶段路线图

### Phase 5：会话与短期记忆

目标：支持多轮会话和滑动窗口。

任务：

1. 新增 `src/petrochat/app/memory/short_term.py`。
2. 扩展 `AgentState`：`session_id`、`user_id`、`conversation_summary`。
3. 新增会话表和消息表。
4. `/api/chat/stream` 支持 `session_id`。
5. 实现最近 N 轮窗口 + 工具结果摘要。
6. 超窗后生成 conversation summary。
7. 增加单元测试：窗口裁剪、摘要更新、session 隔离。

验收：

```text
用户追问“那它的依据是什么”能关联上一轮主题
长对话不会无限增长 prompt
不同 session 不串上下文
```

### Phase 6：长期记忆

目标：跨会话保留用户偏好、项目背景和历史决策。

任务：

1. 新增 `memory_item`、`memory_event` 表。
2. 实现 `memory_write` 节点。
3. 实现 `memory_retriever`。
4. 增加记忆去重、更新、禁用、删除。
5. 前端 Memory 页面展示记忆。
6. 增加 memory eval 样例。

验收：

```text
用户说“以后回答都用 Markdown 表格”
新会话中询问统计问题时自动遵循偏好
用户删除该记忆后不再影响回答
```

### Phase 7：评估集与指标

目标：把项目质量从“能演示”升级为“可量化”。

任务：

1. 建立 RAG 标注集。
2. 建立 NL2SQL golden set。
3. 建立多轮记忆评估集。
4. 实现 `scripts/eval_rag.py`。
5. 实现 `scripts/eval_sql.py`。
6. 实现 `scripts/eval_memory.py`。
7. 在 README 写入最新指标表。

验收：

```text
uv run python scripts/eval_rag.py 输出 Recall@K / MRR
uv run python scripts/eval_sql.py 输出执行准确率
uv run python scripts/eval_memory.py 输出记忆命中率
```

### Phase 8：前端与可观测性增强

目标：让项目可以完整演示“用户、管理员、开发者”三种视角。

任务：

1. 会话历史持久化。
2. 管理员观测台接后端数据。
3. Memory 管理页。
4. Evaluation 看板。
5. LangSmith trace 链接落库。
6. Docker Compose 增加前端服务。

验收：

```text
docker compose up 后可访问前端
管理员能查看所有会话和失败样例
前端能展示评估指标
```

## 7. 推荐提交规划

| Commit | 内容 | 说明 |
| --- | --- | --- |
| `docs(roadmap): add memory evaluation frontend plan` | 本文档 | 先把路线讲清楚 |
| `feat(memory): add session persistence and sliding window` | Phase 5 | 短期记忆 |
| `feat(memory): add long-term memory store and retriever` | Phase 6 | 长期记忆 |
| `test(eval): add rag sql memory evaluation suites` | Phase 7 | 指标体系 |
| `feat(frontend): add session and memory admin views` | Phase 8 | 前端闭环 |
| `chore(docker): add frontend and mysql demo compose` | 部署 | 一键演示 |

## 8. 简历讲法

可以这样描述项目升级后的价值：

> PetroChat-Agent 是一个面向石化领域的多 Agent 智能问答平台。我从单节点 RAG 起步，逐步演进到 Tool Calling、MCP Server、Supervisor 多 Agent、NL2SQL 和报表生成。在 v1.1 规划中，我进一步设计了短期滑动窗口、长期用户记忆、可解释记忆管理和可量化评估体系，使用 Recall@K、MRR、SQL 执行准确率、Memory Hit Rate 等指标持续评估系统质量；前端不仅提供对话入口，还提供管理员观测台、记忆管理和评估看板，用于展示 Agent 路由、工具调用、错误追踪和质量回归。

面试可展开的技术点：

1. 为什么短期记忆不能直接无限塞 messages，而要滑动窗口 + 摘要。
2. 为什么长期记忆要区分用户偏好、业务背景、历史决策和纠错。
3. 为什么规范知识库引用和用户记忆引用必须分开。
4. 如何用 Recall@K / MRR 评估 RAG 召回质量。
5. 如何用执行准确率和安全违规率评估 NL2SQL。
6. 如何把 SSE、LangSmith、管理员观测台结合起来排查 Agent 失败链路。

## 9. 近期最小可执行路径

建议下一步不要同时开太多线，按如下顺序推进：

1. 先做 Phase 5：会话持久化 + 短期滑动窗口。
2. 同时整理 `data/eval/rag_questions.yaml` 和 `data/eval/sql_questions.yaml`。
3. 再做 Phase 7 的 RAG / SQL 基础评估脚本。
4. 然后做 Phase 6 长期记忆。
5. 最后让前端 Admin 接入真实后端会话、记忆和评估数据。

这样每一步都能单独 commit、单独演示，也能在简历中讲成清晰的技术演进。
