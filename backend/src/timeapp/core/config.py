"""Environment-backed application settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量或本地 .env 文件加载运行时配置。"""

    app_name: str = "TimeApp"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://timeapp:timeapp@127.0.0.1:5432/timeapp"
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 30.0
    asr_api_key: str | None = None
    asr_base_url: str = "https://api.openai.com/v1"
    asr_model: str = "whisper-1"
    asr_protocol: str = "openai_transcription"
    asr_language: str = "zh"
    asr_max_audio_bytes: int = 25 * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TIMEAPP_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """获取settings。"""

    return Settings()
