from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки читаются из окружения и из .env. Секреты в коде не хранятся."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    database_path: str = "./data/finritm.sqlite3"
    cors_origins: str = "http://localhost:5173"
    telegram_bot_token: str = ""
    tg_id_salt: str = "dev-salt"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
