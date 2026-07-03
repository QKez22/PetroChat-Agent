## Imported Claude Cowork project instructions

# 项目背景
本项目是 **PetroChat-Agent**——石化领域智能问答与多 Agent 数据分析平台。
基于真实石化规范文档 + 事务/任务业务库，完整跑通 RAG / Tool Calling / MCP / Supervisor 多 Agent / NL2SQL / 报表生成 / 短期+长期记忆 / RBAC + 评估闭环。
目标岗位是 AI/LLM 应用研发方向。

# 技术栈（请严格遵守，不要擅自替换）
- 语言：Python 3.12（部分代码用 `from datetime import timezone; UTC = timezone.utc` 兼容 3.10）
- Agent 编排：LangGraph 1.x（**Supervisor 模式**，supervisor → {qa / sql / general}）
- LLM 应用框架：LangChain
- Web 框架：FastAPI（SSE 流式 + JWT 鉴权）
- 向量库：Chroma HTTP 服务（chromadb-client + Docker chromadb/chroma 镜像）
- 关系库：MySQL 8（**两个账号分离**：业务库只读 + 应用专属库可写）
- 大模型：DeepSeek `deepseek-chat`（OpenAI 兼容协议，function_calling 模式）
- Embedding：阿里云百炼 `text-embedding-v3`（1024 维，OpenAI 兼容）
- MCP：官方 mcp SDK（FastMCP，@mcp.tool() 暴露工具），stdio/HTTP 双传输
- 前端：Vue3 + Vite + fetch SSE + Markdown 渲染（含 base64 图表）
- 依赖管理：uv（pyproject.toml）
- 部署：Docker + Docker Compose（含 mysql / chroma / api / frontend 四服务）

# 项目结构（生成代码时按此归属）
src 布局，`src/petrochat/app/` 下分包：
- **api**：FastAPI 路由（chat SSE / sessions / memory / auth / admin / evaluation）
- **agent**：LangGraph Supervisor StateGraph + 四节点（supervisor/qa/sql/general）+ tools 子图
- **rag**：文档解析 / 向量库 CRUD / 检索器
- **sql**：NL2SQL 四件套（engine / generator / validator / executor）+ schema 抓取
- **report**：DataFrame → Markdown 表 + matplotlib 图表（base64 PNG 侧信道）
- **tools**：领域工具（convert_unit / lookup_section / search_within_doc / retrieve_specs）
- **mcp**：FastMCP Server + langchain-mcp-adapters 客户端
- **memory**：短期会话存储 + 长期记忆（MySQL agent_* 表）+ 上下文注入
- **evaluation**：Golden Set 评估 + 回放 + baseline + 质量门禁
- **core**：配置（pydantic-settings + SecretStr）/ LLM 客户端 / AgentState / 实体 / LangSmith
- **retention**：数据保留与清理任务

状态对象用 TypedDict，路由字段用 Literal（`Literal["qa","sql","general","tool","scoring","FINISH"]`）。

# MySQL 双账号约定（重要）
- `MYSQL_USER` / `MYSQL_PASSWORD`：业务库只读账号（NL2SQL 走这个，仅 SELECT）
- `MYSQL_APP_USER` / `MYSQL_APP_PASSWORD`：应用专属账号，对 `agent_*` 表有 CRUD 权限
  （memory / sessions / audit / evaluation 写库走这个）
- 两个账号都连同一个 database；权限通过 GRANT 区分。

# 开发节奏
项目已完成四阶段（v0.1-rag / v0.2-tool / v0.3-mcp / v1.0-multiagent），
后续维护以 **v1.x** 演进（记忆 / 评估 / RBAC / 前端 / Docker demo），不再回头叠加废弃方向（如三维质检评分）。

# 协作偏好
1. 用中文回答。
2. 代码规范、可运行、有必要的中文注释，符合 Python 工程实践（类型标注、Pydantic 校验）。
3. 给出关键设计决策的理由，不只是给代码。
4. LangGraph / LangChain / MCP SDK 迭代快，涉及 API 时注意版本，必要时提醒核对。
5. 生成 README、接口文档、提交说明时，突出项目的工程价值与垂直领域特色。
6. 不确定的地方先问，不要臆造需求。
