# RAG 升级执行记录

分支：`codex/rag-evidence`。保留 DeepSeek、百炼 text-embedding-v3、Chroma HTTP 和现有 Supervisor。

私有语料、原文片段、评测问题及运行结果只写入 ignored 的 `data/runtime/`，不提交远程。

## 步骤 1：语料与标注校准

新增 `scripts/prepare_rag_corpus.py`，生成由文件内容和解析结果决定的可复现快照及标注审计报告。原始标签保持不变；未解析文档、占位 ID 和错误条款标记为待核对，不自动生成满分标签。证据匹配改为字段级匹配，并统一 `.docx` 文件名和向量元数据的文档标识。

执行示例：`uv run python scripts/prepare_rag_corpus.py --raw-dir data/raw --golden-dir data/ducuments/agent_memory_golden_set`。

旧 `.doc` 在缺少转换器时暂时排除，保留原件及审计记录。独立检索基准的每个证据 ID 必须附带可在原文逐字核对的引文。Oracle 产物只用于评测管道自测。
