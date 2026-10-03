# RAG 升级执行记录

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
