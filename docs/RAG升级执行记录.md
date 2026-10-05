# RAG 升级执行记录

2026-10-05：完成第二轮原因诊断与 `adaptive_hybrid` 实现；20 道新冻结题上相对向量 Recall@5 +15 个百分点、MRR +0.1725；相对第一轮减少 70% 重排调用。中位延迟改善，但 P95 未稳定改善。范围、方法、复测结果及限制详见 `RAG第二轮优化报告.md`。

分支：`codex/rag-evidence`。保留 DeepSeek、百炼 text-embedding-v3、Chroma HTTP 和现有 Supervisor。

私有语料、原文片段、评测问题及运行结果只写入 ignored 的 `data/runtime/`，不提交远程。

## 步骤 1：语料与标注校准

新增 `scripts/prepare_rag_corpus.py`，生成由文件内容和解析结果决定的可复现快照及标注审计报告。原始标签保持不变；未解析文档、占位 ID 和错误条款标记为待核对，不自动生成满分标签。证据匹配改为字段级匹配，并统一 `.docx` 文件名和向量元数据的文档标识。

执行示例：`uv run python scripts/prepare_rag_corpus.py --raw-dir data/raw --golden-dir data/ducuments/agent_memory_golden_set`。

旧 `.doc` 在缺少转换器时暂时排除，保留原件及审计记录。独立检索基准的每个证据 ID 必须附带可在原文逐字核对的引文。Oracle 产物只用于评测管道自测。

本地审计：2 份 DOCX、1121 个片段；2 份 DOC 暂排除，110 条旧标签尚未解析为可靠真值。另建立 16 道逐条核对原文的小样本（12 开发、4 留出），只用于早期检索回归，不宣称代表整个领域。步骤 1 相关测试：9 项通过。

## 步骤 2：精确查条款、文档过滤与真实基线

`lookup_section` 通过 Chroma metadata 分页读取完整条款，不调用 embedding；指定文档检索先解析文档名，再下推文档条件。新增独立的 RAG 基准执行器，分别记录 Recall@5、完整证据覆盖率、MRR 与 P95。

`benchmark_rag.py --backend snapshot` 用真实百炼向量和当前语料做精确余弦检索，缓存以语料快照和模型配置隔离；`--backend chroma` 调用实际 Chroma。两种后端分别标注，精确检索结果不作为 Chroma ANN 集成验证。缓存命中后的耗时不代表冷启动网络耗时。

步骤 2 验证：16 项相关测试通过；12 道开发题的真实百炼精确向量基线 Recall@5=10/12、MRR=0.8333。样本较小，留出题未用于调参。

## 步骤 3：混合检索与真实重排

新增中文分词 BM25、去重 RRF、百炼 `gte-rerank-v2` 重排；QA、跨文档工具和指定文档工具使用同一检索器。关键词候选和向量候选使用同一文档过滤条件。重排超时或响应不合法时保留 RRF 排序，并在元数据和评测中显式记录降级；引用保留修订版本名称。

可通过 `RAG_MODE=vector|hybrid|hybrid_rerank` 切换；默认 `hybrid_rerank`，候选 30、返回 5。配置包含重排模型、URL、超时，不新增硬编码密钥。新增依赖使用独立 worktree 的 Python 3.12 环境，不修改原项目环境。

同一快照、同一 12 道开发题：向量 Recall@5=10/12，RRF=11/12，RRF+真实重排=12/12、MRR=0.9583、重排降级 0 次。重排 P95 约 850ms（包含重排 HTTP，但查询 embedding 命中缓存，不能视为生产端到端延迟）。留出题仍未用于调参。

Docker 启动后补跑验证：32 项全部通过，无跳过，包含真实 Chroma HTTP + 百炼 embedding/重排集成测试。使用独立临时测试集合并在测试后清理，未重置业务集合。jieba 有 3 条上游正则转义 SyntaxWarning，不影响执行。

## 步骤 4：版本策略与原子快照

新增 MySQL `agent_rag_manifest` / `agent_rag_active` 保存不可变版本与权限清单、内容哈希和活动索引指针。构建使用新 Chroma 集合，完整写入后事务切换；失败不覆盖旧集合。所有读路径共用请求级身份、业务日期及快照，向量、BM25、精确查询和一跳引用扩展统一过滤。有效期为 `[from, to)`；未知版本不支持指定日期的有效性断言，重叠版本阻断查询。

兼容迁移：默认 `RAG_CATALOG_ENABLED=false`，保持旧索引可用，但此模式不提供版本/文档权限保证。完成管理员建表、显式策略清单发布后设置为 `true` 并重启 API；未提供身份上下文或发布快照时拒绝查询。新增聊天可选字段 `rag_as_of`（ISO 日期）；身份来自现有 JWT 解析路径。版本 ID 和 document_id 需管理员核对，同一规范不同版本应使用相同 document_id。`allowed_users` 默认空列表（拒绝所有访问），`["*"]` 表示现有全体登录用户共享，仅由管理员显式填写。

发布命令：`uv run python scripts/publish_rag_snapshot.py --corpus data/runtime/rag/corpus.json --policies data/runtime/rag/policies.json`。策略清单为 VersionPolicy 对象列表，字段含 source_doc、document_id、version_id、status、effective_from、effective_to、allowed_users。未知日期必须用 status=unknown，不使用文件名年份替代生效日。

阶段验证：19 项版本策略/Chroma 检索测试通过；29 项现有 Agent runtime/API 回归通过。真实 MySQL 建表被应用账号正确拒绝（CREATE denied），未提升权限、未发布新活动索引。管理员执行 `scripts/migrations/004_rag_catalog.sql` 后继续验收，再提交步骤 4。原文关系当前按规则按需解析，仅扩展同版本明确的条款号，最多一跳四个片段；跨文档、表格脚注及人工核对关系管理尚未覆盖。

管理员执行迁移后，已核实两张表均具备 SELECT/INSERT/UPDATE/DELETE 权限。真实 MySQL + Chroma 已成功发布 1121 片段的新快照并完成带授权过滤的混合检索；原集合未覆盖。现有两份文档仍标记 unknown，仅作为参考资料，不支持历史有效性断言。默认配置保持兼容模式，生产启用版本权限策略需显式设置 RAG_CATALOG_ENABLED=true。

## 步骤 5：结论级证据校验与有界补检

QA 改为 LangGraph 子图：检索/一跳扩展、结构化结论生成、引用存在性与逐字引文校验、数字保护、模型支撑性和问题覆盖审核。最多两轮检索与生成，权限/版本失败或缺业务条件直接停止。失败的草稿不写入消息，SSE 仍只交付已完成 worker 的验证后正文。模型审核不是正确性概率，也不能替代专业人员判断。

每条结论附后端生成的稳定证据 ID，最终结果新增 evidence（原文、引文、条款、版本、快照）及 rag_status。未知日期文档显式标为仅供参考；历史语境缺日期先追问。受保护模式下 MCP 的 RAG 工具替换为请求内本地工具，避免远端缺失权限上下文。普通工具问答仍不等同于 QA 子图的逐结论审核。

验证：84 项引用/预算/任务/API/语义契约回归通过。真实 MySQL + Chroma + 百炼 + DeepSeek QA 调用成功，5 项证据引文逐字匹配；该单题仅用于端到端冒烟，不作为总体正确率。

## 步骤 6：原文预览、前端与验收

新增 JWT 鉴权原文预览、Vue 证据卡片、规范适用日期输入和子图阶段进度。前端使用文本插值展示原文，不将原文作为 HTML 执行。历史消息可从正文恢复稳定引用 ID，再经当前权限校验查看原文；旧快照或历史日期信息未保留时不回退到不受控的缓存。

121 项 Python 回归通过；前端 pnpm 锁文件安装、生产构建及组件 SSR 测试通过。真实预览返回与生成证据一致的原文，未知日期历史请求返回 404。上游 jieba 正则转义、Chroma telemetry 兼容警告不影响上述验证。

冻结方案后执行 4 道留出题：真实 Chroma 向量与混合重排 Recall@5 均为 0.75；MRR 从 0.5625 变为 0.4583，重排 P95 更高。因此验收阶段默认回退到 vector，hybrid/hybrid_rerank 作为显式配置保留；没有用留出题继续调整召回或模型参数。完整结果、启用方式、功能边界与可写简历表述见 `RAG验收与简历说明.md`。
