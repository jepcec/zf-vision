from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    BACKEND_URL: str = "http://localhost:8000"
    MOCK_BACKEND: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8765
    LOG_LEVEL: str = "INFO"
    PUSH_INTERVAL_S: int = 5


def get_settings() -> Settings:
    return Settings()
