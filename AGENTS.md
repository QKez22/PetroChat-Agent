## Imported Claude Cowork project instructions

# 项目背景
本项目是 PetroChat-Agent —— 石化领域智能问答与质检 Agent 平台，是一个用于学习 Agent 技术栈、可写进简历的个人项目。基于真实石化行业 Q&A 数据集，覆盖 RAG、Tool Calling、MCP、多 Agent 协作四大能力。目标岗位是 AI/LLM 应用研发方向。

# 技术栈（请严格遵守，不要擅自替换）
- 语言：Python 3.12
- Agent 编排：LangGraph 1.x（Supervisor 模式）
- LLM 应用框架：LangChain
- Web 框架：FastAPI（SSE 流式输出）
- 向量库：Chroma（起步）/ PGVector（进阶）
- 大模型：通义千问 / DeepSeek API
- MCP：官方 mcp SDK（FastMCP，@mcp.tool() 暴露工具）
- 前端：Vue3（前后端分离）
- 依赖管理：uv（pyproject.toml）
- 部署：Docker + Docker Compose

# 项目结构（生成代码时按此归属）
src 布局，src/petrochat/app/ 下分包：api（路由+SSE）、agent（LangGraph 编排与节点）、rag（检索增强）、quality（三维质检评分）、tools（领域工具）、mcp（MCP Server）、core（配置/状态/实体）。状态对象用 TypedDict，路由字段用 Literal。

# 开发节奏
按四阶段迭代：① RAG 问答 ② Tool Calling ③ MCP Server ④ 多 Agent 协作。当前处于第【4】阶段，请聚焦该阶段，不要超前实现后续阶段功能。

# 协作偏好
1. 用中文回答。
2. 代码规范、可运行、有必要的中文注释，符合 Python 工程实践（类型标注、Pydantic 校验）。
3. 给出关键设计决策的理由，不只是给代码。
4. LangGraph / LangChain / MCP SDK 迭代快，涉及 API 时注意版本，必要时提醒我核对。
5. 生成 README、接口文档、提交说明时，突出项目的工程价值与垂直领域特色。
6. 不确定的地方先问我，不要臆造需求。
