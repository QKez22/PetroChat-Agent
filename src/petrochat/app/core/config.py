"""集中配置管理。

设计要点：
1. 用 pydantic-settings 自动从 .env 加载配置 + 类型校验，避免散落的 os.getenv 调用。
2. 用 @lru_cache 做单例，整个应用生命周期共享一份配置。
3. 字段名与 .env 中的环境变量名严格一一对应（大小写不敏感）。
4. 敏感字段（API Key）用 SecretStr，避免被日志或 repr 意外打印。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（用于定位 .env、chroma_db 等）
# core/config.py → app/core/config.py → 向上四层到项目根
PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    """应用全局配置。

    所有字段会自动从环境变量或 .env 文件加载，对应关系按字段名（不区分大小写）。
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # 允许 .env 中存在未声明的字段（如 conda 的变量），但不会读入
    )

    # ---------- 应用 ----------
    app_env: str = Field(default="dev", description="运行环境：dev / prod")
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")

    # ---------- DeepSeek（Chat / Reasoner）----------
    deepseek_api_key: SecretStr = Field(default=SecretStr(""))
    deepseek_base_url: str = Field(default="https://api.deepseek.com/v1")
    deepseek_chat_model: str = Field(default="deepseek-chat")
    deepseek_reasoner_model: str = Field(default="deepseek-reasoner")

    # ---------- 阿里云百炼（Embedding）----------
    dashscope_api_key: SecretStr = Field(default=SecretStr(""))
    dashscope_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    embedding_model: str = Field(default="text-embedding-v3")
    embedding_dim: int = Field(default=1024)

    # ---------- Chroma 向量库 ----------
    chroma_host: str = Field(default="localhost")
    chroma_port: int = Field(default=8001)
    chroma_collection: str = Field(default="petrochat_specs")

    # ---------- LangSmith ----------
    langsmith_tracing: bool = Field(default=False)
    langsmith_api_key: SecretStr = Field(default=SecretStr(""))
    langsmith_project: str = Field(default="petrochat-agent")
    langsmith_endpoint: str = Field(default="https://api.smith.langchain.com")

    # ------------------------------------------------------------------
    # 派生属性（不从环境变量读，从其它字段计算）
    # ------------------------------------------------------------------
    @property
    def chroma_url(self) -> str:
        """Chroma 服务的完整 HTTP URL。"""
        return f"http://{self.chroma_host}:{self.chroma_port}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取全局配置单例。

    用 lru_cache 实现单例：第一次调用时创建并缓存，后续调用直接返回缓存对象。
    这是 pydantic-settings 官方推荐的模式，比模块级单例对测试更友好
    （测试中可以用 get_settings.cache_clear() 强制重新加载）。
    """
    return Settings()
