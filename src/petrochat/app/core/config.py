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

    app_env: str = Field(default="dev")
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")

    deepseek_api_key: SecretStr = Field(default=SecretStr(""))
    deepseek_base_url: str = Field(default="https://api.deepseek.com/v1")
    deepseek_chat_model: str = Field(default="deepseek-chat")
    deepseek_reasoner_model: str = Field(default="deepseek-reasoner")

    dashscope_api_key: SecretStr = Field(default=SecretStr(""))
    dashscope_base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    embedding_model: str = Field(default="text-embedding-v3")
    embedding_dim: int = Field(default=1024)
    embedding_batch_size: int = Field(default=10)

    chroma_host: str = Field(default="localhost")
    chroma_port: int = Field(default=8001)
    chroma_collection: str = Field(default="petrochat_specs")

    langsmith_tracing: bool = Field(default=False)
    langsmith_api_key: SecretStr = Field(default=SecretStr(""))
    langsmith_project: str = Field(default="petrochat-agent")
    langsmith_endpoint: str = Field(default="https://api.smith.langchain.com")

    mcp_enabled: bool = Field(default=False)
    mcp_transport: str = Field(default="stdio")
    mcp_server_command: str = Field(default="python")
    mcp_server_args: str = Field(default="-m petrochat.app.mcp.server")
    mcp_server_url: str = Field(default="http://localhost:8765/mcp")

    mysql_host: str = Field(default="localhost")
    mysql_port: int = Field(default=3306)
    mysql_database: str = Field(default="timing_task")
    mysql_user: str = Field(default="timing_reader")
    mysql_password: SecretStr = Field(default=SecretStr(""))
    sql_default_limit: int = Field(default=1000)
    sql_timeout_seconds: int = Field(default=10)
    mysql_tables_whitelist: str = Field(default="affair,affair_task")
    mysql_enum_sample_threshold: int = Field(default=30)
    auth_secret_key: SecretStr = Field(default=SecretStr("petrochat-dev-secret-change-me"))
    auth_token_expire_minutes: int = Field(default=480)
    auth_allow_plaintext_passwords: bool = Field(default=True)
    retention_conversation_days: int = Field(default=180)
    retention_conversation_recovery_days: int = Field(default=30)
    retention_tool_log_days: int = Field(default=365)
    retention_retrieval_context_days: int = Field(default=90)
    retention_audit_log_days: int = Field(default=1095)
    retention_temp_file_days: int = Field(default=30)

    short_term_turns: int = Field(default=6)
    long_term_memory_limit: int = Field(default=5)
    eval_results_path: Path = Field(
        default=PROJECT_ROOT / "data" / "eval_results" / "golden_eval_summary.json"
    )
    eval_predictions_path: Path = Field(
        default=PROJECT_ROOT / "data" / "eval_results" / "predictions.jsonl"
    )

    @property
    def chroma_url(self) -> str:
        return f"http://{self.chroma_host}:{self.chroma_port}"

    @property
    def mysql_url(self) -> str:
        pw = self.mysql_password.get_secret_value()
        return (
            f"mysql+pymysql://{self.mysql_user}:{pw}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    @property
    def mysql_whitelist(self) -> list[str]:
        return [t.strip() for t in self.mysql_tables_whitelist.split(",") if t.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
