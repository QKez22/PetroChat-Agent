# Phase 9.1 权限生产化

## 目标

把前端演示 token 升级为可签名、可过期、可通过 Header 传输的认证机制，并为后续完整 RBAC、审计和生产部署打基础。

## 本阶段已实现

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 签名 token | 已完成 | 登录后返回 HMAC-SHA256 签名的 JWT 风格 token，包含 `sub/user_id/username/role/authority_flag/iat/exp` |
| token 过期 | 已完成 | 由 `AUTH_TOKEN_EXPIRE_MINUTES` 控制，默认 480 分钟 |
| Bearer Header | 已完成 | `/api/auth/me` 与 `/api/admin/*` 支持 `Authorization: Bearer <token>` |
| query token 兼容 | 已完成 | 保留 `?token=` 兼容旧前端和测试，但新前端已改用 Header |
| 管理员接口守卫 | 已完成 | `/api/admin/overview`、`/api/admin/conversations`、`/api/admin/tool-logs`、`/api/admin/audit-logs` 统一走 `require_admin` |
| 密码哈希兼容 | 已完成 | 支持 `pbkdf2_sha256$iterations$salt$digest`；开发环境兼容当前明文密码 |
| 哈希生成脚本 | 已完成 | `uv run python scripts/hash_password.py --password <plain>` |

## 环境变量

```env
AUTH_SECRET_KEY=change-me-to-a-long-random-secret
AUTH_TOKEN_EXPIRE_MINUTES=480
AUTH_ALLOW_PLAINTEXT_PASSWORDS=true
```

生产环境要求：

```env
APP_ENV=prod
AUTH_SECRET_KEY=<strong-random-secret>
AUTH_ALLOW_PLAINTEXT_PASSWORDS=false
```

## 密码迁移

当前 demo 和你的现有 `user` 表仍可使用明文密码。迁移时先生成哈希：

```powershell
uv run python scripts/hash_password.py --password admin
```

然后写回 MySQL：

```sql
UPDATE `user`
SET password = 'pbkdf2_sha256$260000$...'
WHERE username = 'admin';
```

工程师账号同理。迁移完成后，把生产环境的 `AUTH_ALLOW_PLAINTEXT_PASSWORDS` 设置为 `false`。

## 前端变化

前端仍把 token 存在 `localStorage`，但调用方式已从 URL query 切到 Header：

```http
Authorization: Bearer <token>
```

这样管理员接口不会再把 token 暴露在普通 URL、浏览器地址或代理访问日志的 query string 中。

## 边界

本阶段是生产化认证基础版，不是完整企业级 IAM：

- 尚未实现 refresh token。
- 尚未实现密码重置、登录失败锁定和验证码。
- 尚未实现每个业务接口的细粒度权限点校验。
- 尚未实现 HTTPS、CSRF、设备管理和 token 黑名单。

下一阶段建议继续做 Phase 9.2：会话、工具日志、RAG 上下文、审计日志的数据保留任务和定期清理策略。
