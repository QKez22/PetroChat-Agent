# Phase 10.1 评估质量门禁

## 目标

把 Golden Set 评估从“生成一组指标”推进到“能判断本次回放是否可接受”。本阶段新增质量门禁基础版，让管理员、脚本和后续 CI 都能用同一套结构化结果判断 Agent 是否出现回归。

## 本阶段已实现

- `src/petrochat/app/evaluation/golden_set.py`：新增 `build_quality_gate`，统一计算 pass / warn / fail / profile-only。
- `scripts/eval_golden_set.py`：新增 `--fail-on-gate`，当门禁状态为 fail 时返回退出码 2。
- `/api/evaluation/latest`：返回 `qualityGate`，管理员前端可直接展示当前评估摘要的门禁状态。
- `/api/evaluation/runs`：每个历史评估批次返回简化版 `qualityGate`，用于批次对比。
- Vue3 管理员评估面板：新增质量门禁卡片，并在运行历史中展示每批次门禁状态。
- `.env.example` / `docker-compose.yml`：新增门禁阈值配置。

## 门禁指标

| 指标 | 默认阈值 | 失败等级 | 说明 |
| --- | --- | --- | --- |
| SQL 模板通过率 | >= 0.95 | fail | Golden Set 中期望 SQL 必须通过 AST 校验 |
| 写操作违规数 | == 0 | fail | NL2SQL 只允许只读 SELECT |
| SELECT * 违规数 | == 0 | warn | 鼓励显式字段，降低过宽查询风险 |
| Agent 成功率 | >= 0.95 | fail | 真实回放不能出现大量系统异常 |
| SQL 校验率 | >= 0.95 | fail | 生成 SQL 必须稳定通过安全校验 |
| SQL 合约准确率 | >= 0.85 | warn | 同时检查合法性、期望表和过滤条件 |
| RAG Recall@5 | >= 0.85 | warn | 标注证据应进入 Top-5 检索结果 |
| RAG MRR | >= 0.65 | warn | 证据越靠前，检索排序越可靠 |
| 忠实性代理指标 | >= 0.85 | warn | 基于检索命中、非空回答和 forbidden points |
| Memory Hit Rate | >= 0.80 | warn | 需要继承记忆的轮次应命中 |
| 记忆忽略违规率 | <= 0.0 | fail | 应忽略的旧条件不能污染回答 |
| 平均延迟 | <= 15000ms | warn | 用于发现工具、数据库或模型变慢 |

## 运行命令

```powershell
# 只生成画像和合约指标，不调用模型
uv run python scripts/eval_golden_set.py

# 对 prediction JSONL 计算指标和质量门禁
uv run python scripts/eval_golden_set.py --prediction-path data/eval_results/predictions.jsonl

# 门禁失败时返回退出码 2
uv run python scripts/eval_golden_set.py --prediction-path data/eval_results/predictions.jsonl --fail-on-gate

# 真实 Agent 小批量回放后立即评估
uv run python scripts/replay_golden_set.py --mode agent --limit 5 --evaluate
```

## API 输出

`GET /api/evaluation/latest` 会返回：

```json
{
  "qualityGate": {
    "status": "warn",
    "label": "预警",
    "summary": "2 项检查需要关注。",
    "failedCount": 0,
    "warningCount": 2,
    "checks": []
  }
}
```

`GET /api/evaluation/runs` 会为每个批次返回简化门禁状态，用于管理员页面对比。

## 阶段边界

- 当前门禁是规则版，不调用额外 LLM-as-judge。
- 当前门禁只基于聚合指标和 prediction JSONL，不暴露完整真实问题、完整 SQL、完整检索片段。
- `profile-only` 表示只跑了 Golden Set 画像，没有 prediction 文件，不等价于真实 Agent 质量通过。

## 面试讲法

这一阶段的价值在于把“可演示指标”推进到“可回归治理”。项目不只展示 RAG Recall、SQL 校验率和 Memory Hit Rate，还把这些指标固化为门禁：失败时 CLI 可返回非 0，管理员页面能看到未通过项，LangSmith trace 线索可以继续定位失败样例。

## 下一步

Phase 10.2 建议做真实 Agent 回放基线：固定 10 到 20 条不含私有原文的演示样例，记录真实 DeepSeek + Chroma + MySQL 在线回放结果，并把截图和指标变化写入评估展示报告。
