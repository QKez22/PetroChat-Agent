# PetroChat-Agent

> 石化领域智能问答与质检 Agent 平台 —— 一个用真实石化标准规范数据集，把 RAG / Tool Calling / MCP / 多 Agent 协作四大能力完整跑通的 Python 工程实践项目。

[![Phase 1](https://img.shields.io/badge/phase--1-RAG%20%E9%97%AE%E7%AD%94-brightgreen)](#)
[![Python](https://img.shields.io/badge/python-3.12-blue)](#)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.x-orange)](#)

## 项目特色

- **垂直领域护城河**：基于真实的中石化炼化企业设备完整性管理体系规范（4 份共 1500+ 条款），具备通用 Agent 项目缺乏的领域纵深。
- **独有质检节点（规划中）**：三维评分 Agent（正确性 / 完整性 / 有用性），将答案质量评估闭环纳入系统。
- **完整工程能力栈**：一个项目同时覆盖 RAG / Tool Calling / MCP / 多 Agent 四大主流能力。
- **对齐主流生态**：LangGraph 1.x + 官方 MCP SDK + FastAPI + Chroma HTTP，紧贴 2026 年 AI 应用研发主流技术栈。

## 技术栈

| 模块 | 选型 |
| --- | --- |
| 语言 | Python 3.12 |
| Agent 编排 | LangGraph 1.x（Supervisor 模式预留） |
| LLM 应用框架 | LangChain |
| Web 框架 | FastAPI（SSE 流式输出） |
| 向量库 | Chroma（HTTP 服务，Docker 部署） |
| Chat / 推理 | DeepSeek `deepseek-chat`（OpenAI 兼容） |
| Embedding | 阿里云百炼 `text-embedding-v3`（1024 维） |
| 链路追踪 | LangSmith |
| MCP | 官方 mcp SDK（FastMCP，第三阶段） |
| 依赖管理 | uv |
| 部署 | Docker + Docker Compose |

## 项目结构

```
PetroChat-Agent/
├── pyproject.toml          # uv 项目与依赖定义
├── docker-compose.yml      # Chroma 容器
├── .env.example
├── data/raw/               # 原始规范文档（不提交）
├── scripts/                # 离线脚本
│   ├── convert_doc.py      # .doc → .docx 批量转换
│   ├── ingest.py           # 全量入库
│   ├── ask.py              # 命令行问答
│   └── check.py            # 检索结果检视
├── tests/
└── src/petrochat/
    ├── main.py             # FastAPI 入口
    └── app/
        ├── api/            # 路由 + SSE
        ├── agent/          # LangGraph 编排
        │   ├── graph.py
        │   ├── prompts.py
        │   └── nodes/qa_node.py
        ├── rag/            # 文档解析 + 向量库 + 检索器
        │   ├── parser.py
        │   ├── vector_store.py
        │   └── retriever.py
        ├── core/           # 配置 / 状态 / 实体 / LLM 客户端 / 可观测性
        ├── quality/        # 三维质检（第四阶段）
        ├── tools/          # 领域工具（第二阶段）
        └── mcp/            # MCP Server（第三阶段）
```

## 开发阶段路线图

| 阶段 | 主题 | 状态 | Tag |
| --- | --- | --- | --- |
| **① RAG 问答** | 单 Agent + 检索增强 | ✅ 完成 | `v0.1-rag` |
| ② Tool Calling | Agent 自主调用工具 | 待启动 | `v0.2-tool` |
| ③ MCP Server | 工具与主体解耦 | 待启动 | `v0.3-mcp` |
| ④ 多 Agent 协作 | Supervisor + 评分闭环 | 待启动 | `v1.0-multiagent` |

## 第一阶段已交付（v0.1-rag）

- [x] uv + src-layout 工程脚手架
- [x] 配置层（pydantic-settings + SecretStr）
- [x] 双策略文档解析器（outlineLvl + 编号正则）
- [x] Chroma HTTP 向量库 7 个原子操作
- [x] 全量入库脚本（按文件幂等更新 + dry-run）
- [x] 检索器（LangChain BaseRetriever 适配）
- [x] LangGraph 单节点 RAG（StateGraph）
- [x] FastAPI 双端点（非流式 + SSE 流式 token 级推送）
- [x] LangSmith 链路追踪

**当前能力**：把石化规范喂给系统后，可以用流式接口问答，答案带 `[N.N.N]` 章节引用 + 末尾列出引用文档。

## 快速开始

### 1. 安装 uv 与依赖

```powershell
# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
cd D:\Project\pythonProject\PetroChat-Agent
uv sync
```

### 2. 配置环境变量

```powershell
copy .env.example .env
notepad .env   # 填入 DEEPSEEK_API_KEY / DASHSCOPE_API_KEY / LANGSMITH_API_KEY
```

### 3. 启动 Chroma

```powershell
docker compose up -d chroma
```

### 4. 把规范放进 `data/raw/`，全量入库

```powershell
# 如果是 .doc 旧格式，先转换
uv run python scripts/convert_doc.py data/raw/

# 入库（首次约 3-5 分钟）
uv run python scripts/ingest.py
```

### 5. 启动 API 服务

```powershell
uv run uvicorn petrochat.main:app --reload --port 8000
```

打开 http://localhost:8000/docs 即可在 Swagger UI 玩。

### 6. 命令行问答（不需启动服务）

```powershell
uv run python scripts/ask.py "什么是 ITPM 策略"
uv run python scripts/ask.py "设备分级如何划分" --stream
```

## 关键设计决策

### 为什么不用 langchain-chroma？

`langchain-chroma` 硬依赖完整版 `chromadb`，会拉入 `chroma-hnswlib` 这个在 Windows 上**没有预编译 wheel** 的 C++ 扩展。改用 `chromadb-client`（HTTP only）+ Chroma Docker 服务，避开 MSVC 编译需求，且更贴近生产形态。

### 为什么 Embedding 用阿里云百炼 + Chat 用 DeepSeek？

各取所长。百炼 `text-embedding-v3` 是国内中文 embedding 标杆（8K 上下文、可变维度）；DeepSeek 在中文推理与代码任务上口碑好，且 `reasoner` 模型为第四阶段质检评分预留了 reasoning 能力。两者都通过 OpenAI 兼容协议调用，**只需要 `langchain-openai` 一个客户端**。

### 为什么"标题永远塞进 chunk 内容"？

文件 1 的标题与正文分段，文件 2 的"编号即条款"（如 `1.4.1 备品配件是为满足…`）形态混在一起。统一让标题成为 chunk 内容首行，既兼容两种结构，又让向量检索能命中"目的依据""适用范围"等标题词。

### 为什么 SSE 而不是 WebSocket？

LLM 是单向输出（服务器 → 客户端），SSE 协议天然契合：HTTP/1.1 兼容、无需额外协议升级、Nginx/CDN 都原生支持。WebSocket 适合双向实时（聊天室、协同编辑），LLM 流式属于 SSE 经典场景。

## License

Apache License 2.0
