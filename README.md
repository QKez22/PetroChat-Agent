# PetroChat-Agent

> 石化领域智能问答与质检 Agent 平台 —— 一个用真实石化标准规范数据集，把 RAG / Tool Calling / MCP / 多 Agent 协作四大能力完整跑通的 Python 工程实践项目。

## 项目特色

- **垂直领域护城河**：基于真实石化炼化企业的标准规范文档，具备通用 Agent 项目缺乏的领域纵深。
- **独有质检节点**：内置三维评分 Agent（正确性 / 完整性 / 有用性），将答案质量评估闭环纳入系统。
- **完整工程能力栈**：一个项目同时覆盖 RAG、Tool Calling、MCP、多 Agent 四大主流能力。
- **对齐主流生态**：LangGraph 1.x + 官方 MCP SDK + FastAPI，紧贴 2026 年 AI 应用研发主流技术栈。

## 技术栈

| 模块 | 选型 |
| --- | --- |
| 语言 | Python 3.12 |
| Agent 编排 | LangGraph 1.x（Supervisor 模式） |
| LLM 应用框架 | LangChain |
| Web 框架 | FastAPI（SSE 流式输出） |
| 向量库 | Chroma（起步）/ PGVector（进阶） |
| Chat / 推理 | DeepSeek（OpenAI 兼容） |
| Embedding | 阿里云百炼 `text-embedding-v3`（1024 维） |
| 链路追踪 | LangSmith |
| MCP | 官方 mcp SDK（FastMCP） |
| 依赖管理 | uv |
| 部署 | Docker + Docker Compose |

## 项目结构

```
PetroChat-Agent/
├── pyproject.toml          # uv 项目与依赖定义
├── .env.example            # 环境变量样例
├── .gitignore
├── README.md
├── data/
│   └── raw/                # 原始规范文档（不提交）
├── scripts/                # 离线脚本（切片入库等）
├── tests/                  # 测试
├── docs/                   # 项目文档
└── src/
    └── petrochat/
        ├── main.py         # FastAPI 应用入口
        └── app/
            ├── api/        # 路由与 SSE
            ├── agent/      # LangGraph 编排与节点
            ├── rag/        # 检索增强
            ├── quality/    # 三维质检评分
            ├── tools/      # 领域工具
            ├── mcp/        # MCP Server
            └── core/       # 配置、状态、实体（最底层）
```

## 开发阶段路线图

项目采用四阶段迭代开发，每个阶段都是一个可演示的里程碑：

| 阶段 | 主题 | 点亮的包 | 里程碑 | Tag |
| --- | --- | --- | --- | --- |
| **① RAG 问答**（进行中） | 单 Agent + 检索增强 | `rag` `agent` `api` `core` | 流式问答 + 引用来源 | `v0.1-rag` |
| ② Tool Calling | Agent 自主调用工具 | `tools` | 自动选择工具完成任务 | `v0.2-tool` |
| ③ MCP Server | 工具与主体解耦 | `mcp` | FastMCP 独立服务 | `v0.3-mcp` |
| ④ 多 Agent 协作 | Supervisor + 评分闭环 | `agent` `quality` | 评分过低自动重试 | `v1.0-multiagent` |

## 快速开始

### 1. 安装 uv

```bash
# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Mac / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 同步依赖

```bash
uv sync
```

### 3. 配置环境变量

```bash
# Windows
copy .env.example .env
# Mac / Linux
cp .env.example .env
```

然后编辑 `.env` 填入你的 API Key。

### 4. 启动开发服务器

```bash
uv run uvicorn petrochat.main:app --reload --host 0.0.0.0 --port 8000
```

打开 http://localhost:8000/health 应看到 `{"status":"ok"}`。

## 当前进度

- [x] **步骤 1.1** 工程脚手架（uv + src-layout + 7 个能力包骨架）
- [x] **步骤 1.2** `core` 包：配置、LLM 客户端、AgentState
- [x] **步骤 1.3** 规范文档解析器（python-docx 层级切片）
- [x] **步骤 1.4** Chroma 向量库增删改查
- [x] **步骤 1.5** 入库脚本
- [ ] 步骤 1.6 检索器（向量召回 + 元数据过滤）
- [ ] 步骤 1.7 LangGraph 单节点 RAG
- [ ] 步骤 1.8 FastAPI + SSE 流式接口
- [ ] 步骤 1.9 LangSmith 接入

## 入库工作流

```bash
# 1. 启动 Chroma
docker compose up -d chroma

# 2. 把规范文档放到 data/raw/
# 3. 如有 .doc 旧格式，先转换
uv run python scripts/convert_doc.py data/raw/

# 4. 全量入库
uv run python scripts/ingest.py

# 5. 仅看会切多少 chunk（不入库，秒级）
uv run python scripts/ingest.py --dry-run

# 6. 改了切片逻辑，清空集合重建
uv run python scripts/ingest.py --reset
```

## License

Apache License 2.0
