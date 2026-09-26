"""Настройки приложения. Читаются из окружения и из .env. Секреты в коде не хранятся."""

from datetime import date
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    database_path: str = "./data/finritm.sqlite3"
    cors_origins: str = "http://localhost:5173"
    # Фиксированная «сегодня» для демо (ГГГГ-ММ-ДД). Пусто — настоящая дата.
    app_today: date | None = None
    git_sha: str = "dev"

    llm_provider: str = "fake"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    gigachat_credentials: str = ""
    kb_path: str = "data/knowledge_base/kb.json"
    ask_limit_per_minute: int = 20

    telegram_bot_token: str = ""
    tg_id_salt: str = "dev-salt"

    @field_validator("app_today", mode="before")
    @classmethod
    def _empty_today_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
