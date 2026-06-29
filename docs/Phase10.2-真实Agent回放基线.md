# Phase 10.2 真实 Agent 回放基线

## 目标

在 Phase 10.1 的质量门禁基础上，固化一套“真实 Agent 小批量回放基线”。它不是提交私有样例，而是提交可复现的选择逻辑、运行命令和脱敏报告模板，让本地私有 Golden Set 可以稳定转化为面试可讲的评估闭环。

## 本阶段已实现

- `src/petrochat/app/evaluation/baseline.py`：新增基线选择、计划生成、脱敏 Markdown 报告和执行编排。
- `scripts/run_agent_baseline.py`：新增 Phase 10.2 命令行入口。
- 默认 plan-only：不调用模型，只生成样例选择计划。
- 显式 `--execute-agent`：调用真实 LangGraph Agent，生成 prediction JSONL、评估摘要和脱敏报告。
- 支持 `--scenario-target name=count`：按场景配置选择多少组对话。
- 支持 `--max-turns`：控制真实回放最大轮次数，避免误触发大规模模型调用。
- 支持 `--fail-on-gate`：执行后如质量门禁 fail，返回退出码 2。

## 默认样例选择

默认从私有 Golden Set 中按场景选择对话组：

| 场景 | 默认对话组数 |
| --- | --- |
| `nl2sql_condition_memory` | 4 |
| `rag_sql_hybrid_judgement` | 3 |
| `rag_context_memory` | 3 |
| `report_generation_memory` | 2 |
| `system_permission_memory` | 2 |
| `memory_control_edge_case` | 2 |

选择逻辑是确定性的：按 `dialogue_id` 稳定排序后取前 N 组，不做随机抽样，便于重复回归。

## 运行命令

```powershell
# 只生成基线计划和脱敏报告，不调用 LLM
uv run python scripts/run_agent_baseline.py

# 打印脱敏 JSON 摘要
uv run python scripts/run_agent_baseline.py --print-json

# 真实 Agent 回放，最多 20 轮
uv run python scripts/run_agent_baseline.py --execute-agent --max-turns 20 --eval-user-id 1

# 自定义场景比例
uv run python scripts/run_agent_baseline.py `
  --scenario-target nl2sql_condition_memory=3 `
  --scenario-target rag_context_memory=2 `
  --execute-agent `
  --max-turns 10

# 与质量门禁联动，失败时退出码为 2
uv run python scripts/run_agent_baseline.py --execute-agent --max-turns 20 --fail-on-gate
```

## 本地产物

默认输出目录：

```text
data/eval_results/agent_baseline/
```

主要产物：

| 文件 | 是否提交 | 说明 |
| --- | --- | --- |
| `agent_baseline_plan.json` | 否 | 只包含对话 ID、场景统计、角色统计和轮次统计 |
| `agent_baseline_report.md` | 否 | 脱敏报告，不包含原始问题、完整 SQL、完整检索片段 |
| `agent_baseline_predictions.jsonl` | 否 | 真实 prediction，可能包含原始问题和回答，仅本地调试 |
| `agent_baseline_replay_summary.json` | 否 | 回放成功率、路由分布和延迟摘要 |
| `golden_eval_summary.json` | 否 | 质量指标和 `quality_gate` |

`data/eval_results/` 已在 `.gitignore` 中，不提交远程。

## 隐私边界

- 提交代码和文档中不包含私有 Golden Set 原文。
- 脱敏报告只展示聚合指标、场景分布、角色分布、门禁结果和产物路径。
- prediction JSONL 可能包含真实问题、完整 SQL 或模型回答，只允许保存在本地 ignored 目录。
- 如需把截图放入 README，应只截管理员聚合指标和门禁状态，不截原始问题正文。

## 面试讲法

这一阶段可以说明项目具备真实回归能力：不是只靠离线 oracle，而是能在 DeepSeek、Chroma、MySQL 在线时选择一组固定样例，真实调用 Supervisor Agent，再通过 SQL 合约、RAG Recall/MRR、Memory Hit Rate 和质量门禁判断是否回归。

## 下一步

Phase 10.3 建议做演示材料固化：在本地跑一次真实 baseline，整理脱敏指标截图、LangSmith trace 查询线索和 1 页项目演进故事，放入 `docs/Phase10.3-演示材料与面试讲法.md`。
