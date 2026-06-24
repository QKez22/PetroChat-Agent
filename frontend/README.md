# PetroChat-Agent 前端启动说明

这是 PetroChat-Agent 的 Vue3 + Vite 前端工作台，当前包含：

- 登录页：使用后端 `/api/auth/login`，前端 localStorage 保存本地演示 token。
- 工程师对话台：消费 `POST /api/chat/stream`，渲染 Markdown、工具事件、引用和图表。
- 管理员工作台：按 `admin` 角色展示本地问答观测记录、工具调用、路由、耗时和导出能力。

## 1. 版本要求

Vite 7 需要较新的 Node.js。推荐使用：

```powershell
node -v
# v22.12.0 或更高

pnpm -v
```

如果 `pnpm` 不可用：

```powershell
corepack enable
corepack prepare pnpm@latest --activate
```

如果你之前用 `npm install -g pnpm` 遇到 `EEXIST pnpx`，可以优先使用 `corepack`，不要强行混用 npm 安装依赖。

## 2. 启动后端

在项目根目录执行：

```powershell
cd D:\Project\pythonProject\PetroChat-Agent

uv sync
docker compose up -d chroma
uv run python scripts/ingest.py
uv run uvicorn petrochat.main:app --reload --host 127.0.0.1 --port 8000
```

后端文档地址：

```text
http://127.0.0.1:8000/docs
```

如果需要 NL2SQL，请确认 `.env` 中已经配置 DeepSeek、DashScope 和 MySQL 只读账号。

## 3. 启动前端

在 `frontend` 目录执行：

```powershell
cd D:\Project\pythonProject\PetroChat-Agent\frontend

pnpm install
pnpm dev
```

浏览器打开：

```text
http://localhost:5173
```

Vite 代理已固定转发到：

```text
http://127.0.0.1:8000
```

这里不用 `localhost` 作为代理目标，是为了避免 Windows/Node.js 把 `localhost` 解析到 IPv6 `::1` 后出现 `ECONNREFUSED ::1:8000`。

## 4. 登录账号

后端会优先读取 MySQL 的 `user` 表：

| 字段 | 含义 |
| --- | --- |
| `user_id` | 用户主键 |
| `username` | 账号名 |
| `password` | 明文密码，当前阶段暂按明文比对 |
| `authority_flag` | `1=admin`，`0=engineer` |

如果本地开发环境无法连接 MySQL，非生产环境会提供两个演示账号：

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `admin` | 管理员 |
| `engineer` | `engineer` | 工程师用户 |

当前 token 只保存在前端 localStorage，用于本地演示登录态，不是生产级鉴权方案。

## 5. IDEA 中运行

1. 打开项目根目录 `D:\Project\pythonProject\PetroChat-Agent`。
2. 在 IDEA 的 Node.js 设置中选择 Node.js `v22.12.0` 或更高。
3. Package manager 选择 `pnpm`。
4. 打开 `frontend/package.json`。
5. 点击 `scripts.dev` 左侧运行按钮。
6. 浏览器打开 `http://localhost:5173`。

## 6. 常用命令

```powershell
# 前端开发服务
pnpm dev

# 前端生产构建检查
pnpm build

# 本地预览构建产物
pnpm preview
```

## 7. 常见问题

### 7.1 端口 5173 被占用

查看占用进程：

```powershell
Get-NetTCPConnection -LocalPort 5173 | Select-Object LocalAddress,LocalPort,State,OwningProcess
```

停止进程：

```powershell
Stop-Process -Id <OwningProcess> -Force
```

### 7.2 页面能打开，但显示 API 离线

先确认后端是否运行：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

如果失败，重新启动后端：

```powershell
cd D:\Project\pythonProject\PetroChat-Agent
uv run uvicorn petrochat.main:app --reload --host 127.0.0.1 --port 8000
```

### 7.3 前端请求返回 HTTP 500

这通常说明 FastAPI 后端内部报错，不是前端端口问题。请查看后端终端日志，重点检查：

- DeepSeek / DashScope API Key 是否配置。
- Chroma 是否已启动并完成入库。
- MySQL 是否可连接。
- 当前问题是否触发了 NL2SQL 分支但数据库不可用。

## 8. Git 提交命令

本次前端与登录/RBAC 基础能力建议单独提交：

```powershell
git add src/petrochat/app/api/auth.py `
        src/petrochat/app/api/__init__.py `
        src/petrochat/app/core/models.py `
        tests/test_api.py `
        frontend/src/App.vue `
        frontend/src/services/chatStream.js `
        frontend/src/styles.css `
        frontend/README.md `
        README.md `
        docs

git commit -m "feat: 增加前端登录与管理员工作台"
git push origin main
```
