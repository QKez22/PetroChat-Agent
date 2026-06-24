pnpm dev# PetroChat-Agent Frontend

Vue3 + Vite 前端工作台，包含两个视图：

- 对话：消费后端 `POST /api/chat/stream` SSE 流，渲染 Markdown、工具调用、引用和报表图。
- 管理员：查看浏览器本地记录的最近 50 轮问答，包括路由、耗时、状态、工具事件和图表信息。

对话页会把后端返回的 `session_id` 保存在浏览器 `localStorage` 中；同一会话内继续提问时，后端会加载最近 N 轮消息作为短期滑动窗口。点击“新会话”会清空当前 `session_id`，下一次提问会创建新会话。

## 运行环境

前端使用 Vite 7，需要 Node.js 版本满足：

```text
Node.js >= 20.19 或 >= 22.12
```

推荐版本：

```powershell
node -v
# v22.12.0 或更高

pnpm -v
```

如果 `pnpm` 不可用，先启用或安装：

```powershell
corepack enable
corepack prepare pnpm@latest --activate

# 如果 corepack 不可用，再使用 npm 安装
npm install -g pnpm --force
```

## 启动后端

前端默认通过 Vite 代理访问后端：

```text
http://127.0.0.1:8000
```

这里故意使用 `127.0.0.1`，避免 Windows/Node.js 把 `localhost` 解析到 IPv6 `::1` 后出现 `ECONNREFUSED ::1:8000`。

在项目根目录启动后端：

```powershell
cd D:\Project\pythonProject\PetroChat-Agent

# 安装 Python 依赖
uv sync

# 启动 Chroma
docker compose up -d chroma

# 首次运行需要把规范文档入库
uv run python scripts/ingest.py

# 启动 FastAPI
uv run uvicorn petrochat.main:app --reload --port 8000
```

后端启动后可打开：

```text
http://localhost:8000/docs
http://127.0.0.1:8000/docs
```

如果要使用 NL2SQL，需要 `.env` 中配置 DeepSeek、DashScope、MySQL 只读账号等环境变量。

## 启动前端

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

开发服务固定使用 `5173` 端口，并启用了 `strictPort`。如果看到 Vite 自动打开 `5174`、`5175` 等端口，说明旧的前端进程还在占用端口，请先停掉旧进程后重新执行 `pnpm dev`。

## IDEA 中运行

1. 打开项目根目录 `D:\Project\pythonProject\PetroChat-Agent`。
2. 在 `Settings > Languages & Frameworks > Node.js` 中选择 Node.js 22.12.0 或更高版本。
3. Package manager 选择 `pnpm`。
4. 打开 `frontend/package.json`。
5. 点击 `scripts.dev` 左侧运行按钮。

## 常用命令

```powershell
# 开发服务
pnpm dev

# 生产构建检查
pnpm build

# 本地预览构建产物
pnpm preview
```

## 常见问题

### npm install 报错

本项目已经使用 `pnpm-lock.yaml` 锁定依赖，建议不要混用 `npm install`。如果误用了 npm，可清理后重新安装：

```powershell
cd D:\Project\pythonProject\PetroChat-Agent\frontend

if (Test-Path package-lock.json) { Remove-Item package-lock.json }
if (Test-Path node_modules) { Remove-Item -Recurse -Force node_modules }

pnpm install
```

### 前端页面能打开，但显示 API 离线

说明 Vite 前端已启动，但 FastAPI 后端没有启动或不是 `8000` 端口。请先运行：

```powershell
cd D:\Project\pythonProject\PetroChat-Agent
uv run uvicorn petrochat.main:app --reload --port 8000
```

### 端口 5173 被占用

先查看并停止占用进程：

```powershell
Get-NetTCPConnection -LocalPort 5173 | Select-Object LocalAddress,LocalPort,State,OwningProcess
Stop-Process -Id <OwningProcess> -Force
```

不建议随意换端口，因为 README 和 Vite 代理默认都按 `5173 -> 8000` 的本地开发链路说明。确实需要临时换端口时，可以显式指定：

```powershell
pnpm dev -- --port 5174 --strictPort
```
