# Phase 5.9 评估展示报告

本文用于固化 PetroChat-Agent 当前阶段可公开展示的评估结果、失败分析口径和面试演示截图清单。原始 Golden Set、prediction JSONL 和私有规范数据均位于本地 ignored 目录，不提交远程。

## 1. 评估范围

| 项目 | 当前结果 |
| --- | --- |
| 评估数据来源 | 私有 Golden Set，本地目录 `data/ducuments/agent_memory_golden_set/` |
| 对话组数 | 100 |
| 总轮次 | 390 |
| SQL 期望轮次 | 140 |
| RAG 证据轮次 | 110 |
| 记忆状态轮次 | 390 |
| 回放模式 | `oracle`，不调用真实模型，用于验证评估管道 |
| 评估时间 | 2026-06-24 15:27 |

## 2. 核心指标

| 指标 | 当前值 | 说明 |
| --- | --- | --- |
| SQL 模板通过率 | 100% | 140 / 140 通过 `sqlglot` AST 校验 |
| 写操作违规数 | 0 | 未出现 INSERT / UPDATE / DELETE / DROP 等写操作 |
| SELECT * 违规数 | 0 | SQL 合约检查未发现违规 |
| Prediction 数量 | 390 | oracle prediction JSONL 覆盖全部轮次 |
| SQL 生成覆盖率 | 100% | SQL 期望轮次均有 SQL |
| SQL 校验率 | 100% | 已生成 SQL 均通过只读校验 |
| SQL 表召回 | 100% | 期望表名均被命中 |
| SQL 过滤值召回 | 100% | 期望过滤值均被命中 |
| RAG Recall@5 | 100% | 110 个 RAG 证据轮次在 Top-5 中命中来源 |
| 需继承记忆轮次 | 280 | 多轮条件继承场景 |
| 需忽略记忆轮次 | 90 | 条件覆盖、重置或边界控制场景 |
| 需澄清轮次 | 10 | Golden Set 中显式要求澄清的轮次 |

> 说明：当前指标来自 oracle 回放，表示评估管道、标注合约和前端展示闭环已打通；真实模型质量需要在 Phase 7.1 使用 `--mode agent` 小批量回放后再更新。

## 3. 场景覆盖

| 场景 | 轮次 | 价值 |
| --- | --- | --- |
| NL2SQL 条件记忆 | 120 | 验证多轮业务条件继承、SQL 过滤值和只读约束 |
| RAG + SQL 混合判断 | 80 | 验证规范证据与数据库查询的组合能力 |
| RAG 上下文记忆 | 80 | 验证规范问答中的多轮上下文延续 |
| 报表生成记忆 | 40 | 验证统计结果、Markdown 表格和图表侧信道 |
| 系统权限记忆 | 30 | 验证 admin / engineer 权限边界 |
| 记忆边界用例 | 40 | 验证条件覆盖、忽略历史和澄清逻辑 |

## 4. 失败案例分析口径

当前 oracle 回放没有触发真实失败样例，`/api/evaluation/failures` 的价值在于固定失败分析结构。后续真实 Agent 回放后，按以下维度归因：

| 失败类型 | 判定方式 | 排查入口 |
| --- | --- | --- |
| 路由错误 | Supervisor 路由与期望不一致 | LangGraph 状态、SSE tool/meta 事件 |
| SQL 缺失 | `route=sql` 但没有生成 SQL | NL2SQL generator、validator、schema prompt |
| SQL 不安全 | 非 SELECT、多语句、系统库、写操作 | `sqlglot` AST 校验结果 |
| 过滤值缺失 | 期望过滤值未出现在 SQL 中 | Golden Set expected_filters 对比 |
| RAG 召回缺失 | Top-5 未命中期望来源 | Chroma 检索、chunk 切分、query rewrite |
| 记忆继承错误 | 应继承的业务条件丢失 | 短期滑动窗口、长期记忆召回 |
| 权限越界 | engineer 看到 admin 数据或高危操作 | 权限中间件、工具白名单 |
| 延迟异常 | 单轮耗时超过阈值 | 工具调用次数、数据库查询、LLM 首 token |

## 5. 管理员看板展示点

管理员前端目前可以展示三类评估信息：

1. 聚合指标：`GET /api/evaluation/latest`
2. 失败与风险样例：`GET /api/evaluation/failures?limit=8`
3. 评估运行历史与 Trace 查询线索：`GET /api/evaluation/runs?limit=10`

这些接口只返回聚合指标、截断摘要、表名、来源文件和 trace 查询线索，不返回完整真实问题、完整 SQL 或完整检索片段。

## 6. 截图清单

后续演示或简历材料建议补充以下截图，截图文件可放在 `docs/assets/`，但不要包含私有原文：

| 截图 | 内容 | 用途 |
| --- | --- | --- |
| `admin-eval-summary.png` | 管理员页 Golden Set 聚合指标 | 展示质量闭环 |
| `admin-eval-failures.png` | 失败与风险样例点选详情 | 展示可排障能力 |
| `admin-eval-runs.png` | 评估运行历史和 traceHint | 展示运行批次管理 |
| `swagger-evaluation-api.png` | `/api/evaluation/*` Swagger 接口 | 展示后端 API 完整性 |
| `langsmith-supervisor-trace.png` | Supervisor 路由 trace | 展示 Agent 编排可观测性 |
| `langsmith-sql-trace.png` | SQL 分支 trace | 展示 NL2SQL 排障链路 |

## 7. 面试讲法

可以这样讲：

> 我没有只做一个能聊天的 demo，而是补了面向工程回归的 Golden Set。它覆盖 100 组对话、390 个多轮 turn，包含 RAG、NL2SQL、报表、权限和记忆边界场景。评估脚本能生成聚合指标和 prediction JSONL，后端再把最新指标、失败样例和评估历史暴露给管理员前端。这样我既能演示用户问答，也能从管理员角度解释一次 Agent 失败是路由、检索、SQL、记忆还是模型输出导致的。

## 8. 下一步

Phase 6 开始进入长期记忆：

1. 建立 `user_memory` / `memory_event` 数据模型。
2. 从多轮对话抽取用户偏好和常用业务条件。
3. 在 Agent 调用前合并短期滑动窗口与长期记忆。
4. 在管理员或用户前端提供记忆查看、禁用、删除和审计入口。
