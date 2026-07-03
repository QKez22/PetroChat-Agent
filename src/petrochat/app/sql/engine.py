"""SQLAlchemy 引擎管理 —— 只读 + 超时 + 健康检查。

设计要点：
1. 引擎单例（lru_cache）：连接池由 SQLAlchemy 自动管理，避免重复建立 TCP。
2. **三层只读保障**：
   a) MySQL 用户层面 GRANT SELECT only（最强保障，靠用户配置）
   b) 每次会话 SET SESSION TRANSACTION READ ONLY（皮带 + 吊带）
   c) AST 校验拦截非 SELECT（在 validator.py 里，本文件不管）
3. 单 SQL 执行超时通过 MySQL 8 的 MAX_EXECUTION_TIME hint 实现（毫秒级精度）。
4. pool_pre_ping=True：连接复用前先 ping 一次，避免 MySQL 主动断开导致的"connection lost"。
"""

from __future__ import annotations

from functools import lru_cache

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from ..core.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """获取只读 MySQL 引擎单例。"""
    s = get_settings()
    engine = create_engine(
        s.mysql_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        # MySQL 8.0 默认 utf8mb4，但显式声明更稳
        connect_args={"charset": "utf8mb4"},
        future=True,
    )
    logger.info("MySQL 引擎已创建: {}:{}/{}",
                s.mysql_host, s.mysql_port, s.mysql_database)
    return engine


def healthcheck() -> dict:
    """连接探活：能 SELECT 1 + 拿到 MySQL 版本就算 OK。"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # 强制本会话只读，运行时多一层保险
            conn.execute(text("SET SESSION TRANSACTION READ ONLY"))
            version = conn.execute(text("SELECT VERSION()")).scalar()
            db = conn.execute(text("SELECT DATABASE()")).scalar()
            return {
                "ok": True,
                "version": version,
                "database": db,
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_tables() -> list[str]:
    """列出当前 database 下所有 BASE TABLE（排除视图）。"""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' "
            "ORDER BY TABLE_NAME"
        ))
        return [r[0] for r in result]

@lru_cache(maxsize=1)
def get_app_engine() -> Engine:
    """应用专属 MySQL 引擎（对 agent_* 表可写）。

    与 get_engine() 的只读账号物理分离：业务库 NL2SQL 走 get_engine（只读），
    memory / sessions / audit 走 get_app_engine（写 agent_* 表）。
    未配置 MYSQL_APP_USER 时回退到只读账号 —— 开发期方便，但生产应配独立账号。
    """
    s = get_settings()
    if not s.mysql_app_user:
        logger.warning("MYSQL_APP_USER 未配置，memory/sessions 写库回退到只读账号")
    engine = create_engine(
        s.mysql_app_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        connect_args={"charset": "utf8mb4"},
        future=True,
    )
    logger.info("MySQL 应用引擎已创建（写 agent_* 表）: user={}",
                s.mysql_app_user or s.mysql_user)
    return engine

