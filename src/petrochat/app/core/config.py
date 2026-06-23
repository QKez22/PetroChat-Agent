"""集中配置管理。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用
    app_env: str = Field(default="dev")
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")

    # DeepSeek
    deepseek_api_key: SecretStr = Field(default=SecretStr(""))
    deepseek_base_url: str = Field(default="https://api.deepseek.com/v1")
    deepseek_chat_model: str = Field(default="deepseek-chat")
    deepseek_reasoner_model: str = Field(default="deepseek-reasoner")

    # 阿里云百炼 Embedding
    dashscope_api_key: SecretStr = Field(default=SecretStr(""))
    dashscope_base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    embedding_model: str = Field(default="text-embedding-v3")
    embedding_dim: int = Field(default=1024)
    embedding_batch_size: int = Field(default=10)

    # Chroma
    chroma_host: str = Field(default="localhost")
    chroma_port: int = Field(default=8001)
    chroma_collection: str = Field(default="petrochat_specs")

    # LangSmith
    langsmith_tracing: bool = Field(default=False)
    langsmith_api_key: SecretStr = Field(default=SecretStr(""))
    langsmith_project: str = Field(default="petrochat-agent")
    langsmith_endpoint: str = Field(default="https://api.smith.langchain.com")

    # MCP (Phase 3)
    mcp_enabled: bool = Field(default=False)
    mcp_transport: str = Field(default="stdio")
    mcp_server_command: str = Field(default="python")
    mcp_server_args: str = Field(default="-m petrochat.app.mcp.server")
    mcp_server_url: str = Field(default="http://localhost:8765/mcp")

    @property
    def chroma_url(self) -> str:
        return f"http://{self.chroma_host}:{self.chroma_port}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
