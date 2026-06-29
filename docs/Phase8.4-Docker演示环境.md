# Phase 8.4 Docker 演示环境

## 目标

把 PetroChat-Agent 的演示链路收敛为一条命令启动：

```powershell
docker compose up -d --build
```

启动后包含四个服务：

| 服务 | 端口 | 作用 |
| --- | --- | --- |
| `frontend` | `http://localhost:5173` | Vue3 + Nginx，对外提供前端工作台 |
| `api` | `http://localhost:8000` | FastAPI、SSE、多 Agent、评估和管理员接口 |
| `chroma` | `http://localhost:8001` | Chroma HTTP 向量库 |
| `mysql` | `localhost:3307` | MySQL 8 demo schema，避免占用宿主机 3306 |

## 启动前准备

如果只验证页面、登录、管理员观测和 MySQL 表结构，可以直接启动。

如果要真实问答、RAG 入库或 NL2SQL，请在项目根目录 `.env` 中配置：

```env
DEEPSEEK_API_KEY=...
DASHSCOPE_API_KEY=...
```

Compose 会把宿主机 `.env` 中的模型 Key 透传给 `api` 容器，同时强制把容器内依赖地址切到服务名：

```env
CHROMA_HOST=chroma
CHROMA_PORT=8000
MYSQL_HOST=mysql
MYSQL_PORT=3306
```

## 一键启动

```powershell
cd D:\Project\pythonProject\PetroChat-Agent

docker compose up -d --build
docker compose ps
```

登录账号：

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `admin` | 管理员 |
| `engineer` | `engineer` | 工程师用户 |

打开：

```text
http://localhost:5173
```

后端文档：

```text
http://localhost:8000/docs
```

## RAG 入库

规范文档仍放在本机 `data/raw`，该目录不提交远程。API 容器会挂载整个本机 `data/` 目录，因此可直接在容器中执行入库：

```powershell
docker compose run --rm api uv run python scripts/ingest.py
```

如果要指定目录：

```powershell
docker compose run --rm api uv run python scripts/ingest.py --docs-dir data/raw
```

## 健康检查

```powershell
curl http://localhost:8000/health
curl http://localhost:8000/config
curl http://localhost:5173/health
```

## 数据保留 dry-run

```powershell
docker compose run --rm api uv run python scripts/cleanup_retention.py
```

正式执行：

```powershell
docker compose run --rm api uv run python scripts/cleanup_retention.py --execute --actor-id 1
```

查看日志：

```powershell
docker compose logs -f api
docker compose logs -f frontend
docker compose logs -f mysql
docker compose logs -f chroma
```

## MySQL demo schema

初始化 SQL 位于：

```text
docker/mysql/init/001_demo_schema.sql
```

包含：

- `user`：登录账号，`authority_flag=1` 为 admin，`0` 为 engineer。
- `affair` / `affair_task`：NL2SQL 白名单演示表。
- `agent_conversation` / `agent_message`：会话历史与短期记忆。
- `agent_tool_log` / `agent_audit_log`：管理员观测台数据源。
- `user_memory` / `memory_event`：长期记忆治理数据源。

宿主机连接参数：

```text
host=127.0.0.1
port=3307
database=timing_task
user=petrochat_app
password=petrochat_demo
```

如果 `.env` 中设置了 `MYSQL_USER` / `MYSQL_PASSWORD`，Compose 会优先使用 `.env` 中的值。

## 停止与清理

停止服务但保留数据：

```powershell
docker compose down
```

清理 MySQL volume 和 Chroma 本地目录：

```powershell
docker compose down -v
Remove-Item -Recurse -Force .\chroma_db
```

## 边界说明

当前 compose 是工程演示环境，不是生产部署方案：

- MySQL demo 账号用于跑通前后端链路；生产应拆分业务只读账号与应用写入账号。
- 前端由 Nginx 代理 `/api`、`/health` 和 `/config` 到 API 容器，SSE 已关闭代理缓冲。
- 真实规范文档、Golden Set 结果和本地 Chroma 数据仍不提交远程。
- 生产环境仍需补 JWT、HTTPS、审计留存任务、备份和密钥管理。
