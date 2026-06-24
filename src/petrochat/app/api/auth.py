"""认证与角色信息接口。

当前阶段目标是让 Vue3 前端具备可演示的登录与 RBAC 入口：
- 优先读取业务库中的 `user` 表；
- 密码暂按项目约束使用明文比对；
- 返回给前端的是本地演示 token，不作为生产级鉴权凭据。
"""

from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger
from sqlalchemy import text

from ..core import get_settings
from ..core.models import AuthUser, LoginRequest, LoginResponse
from ..sql.engine import get_engine

router = APIRouter(prefix="/api/auth", tags=["auth"])

ADMIN_PERMISSIONS = [
    "用户管理",
    "角色分配",
    "文档上传、删除、更新",
    "知识库重建",
    "向量索引管理",
    "数据库连接配置",
    "工具/API 配置",
    "Agent 提示词配置",
    "模型参数配置",
    "查看所有问答记录",
    "查看所有工具调用记录",
    "查看系统运行日志",
    "查看质量评估结果",
    "导出数据",
    "删除异常数据",
    "审核工程师提交的问题反馈",
]

ENGINEER_PERMISSIONS = [
    "提出业务问题",
    "查询制度、规范、管理办法",
    "查询设备相关知识",
    "查询巡检、维修、隐患、作业流程",
    "查看知识库检索结果",
    "使用 Agent 生成回答",
    "使用 Agent 生成报告草稿",
    "查询允许范围内的数据库信息",
    "查看自己的历史问答记录",
    "对回答进行反馈",
    "标记回答是否正确",
    "提交知识库补充建议",
]


def _role_from_flag(authority_flag: int) -> str:
    return "admin" if authority_flag == 1 else "engineer"


def _permissions_for_role(role: str) -> list[str]:
    return ADMIN_PERMISSIONS if role == "admin" else ENGINEER_PERMISSIONS


def _make_user(row: dict[str, Any]) -> AuthUser:
    flag = int(row["authority_flag"])
    role = _role_from_flag(flag)
    return AuthUser(
        user_id=str(row["user_id"]),
        username=str(row["username"]),
        role=role,  # type: ignore[arg-type]
        authority_flag=flag,
        permissions=_permissions_for_role(role),
    )


def _encode_local_token(user: AuthUser) -> str:
    payload = {
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role,
        "authority_flag": user.authority_flag,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_local_token(token: str) -> AuthUser:
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        return _make_user(payload)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid local token") from exc


def _load_user_from_mysql(username: str, password: str) -> AuthUser | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT user_id, username, authority_flag
                FROM `user`
                WHERE username = :username AND password = :password
                LIMIT 1
                """
            ),
            {"username": username, "password": password},
        ).mappings().first()
    return _make_user(dict(row)) if row else None


def _load_dev_user(username: str, password: str) -> AuthUser | None:
    """无 MySQL 时的本地演示账号，只在非生产环境启用。"""
    dev_users = {
        "admin": {"user_id": "1", "username": "admin", "password": "admin", "authority_flag": 1},
        "engineer": {
            "user_id": "2",
            "username": "engineer",
            "password": "engineer",
            "authority_flag": 0,
        },
    }
    row = dev_users.get(username)
    if row and row["password"] == password:
        return _make_user(row)
    return None


@router.post("/login", response_model=LoginResponse, summary="登录")
async def login(req: LoginRequest) -> LoginResponse:
    settings = get_settings()
    user: AuthUser | None = None
    try:
        user = _load_user_from_mysql(req.username, req.password)
    except Exception as exc:
        logger.warning("读取 user 表失败，当前环境={}，将尝试本地演示账号: {}", settings.app_env, exc)

    if user is None and settings.app_env != "prod":
        user = _load_dev_user(req.username, req.password)

    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    return LoginResponse(token=_encode_local_token(user), user=user)


@router.get("/me", response_model=AuthUser, summary="解析本地 token")
async def me(token: str) -> AuthUser:
    return _decode_local_token(token)
