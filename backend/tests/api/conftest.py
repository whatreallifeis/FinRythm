from datetime import date

import pytest
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

BOT_TOKEN = "123456:TEST-TOKEN-NOT-REAL"
TODAY = date(2026, 9, 26)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        database_path=str(tmp_path / "test.sqlite3"),
        app_today=TODAY,
        telegram_bot_token=BOT_TOKEN,
        tg_id_salt="test-salt",
        llm_provider="fake",
        kb_path=str(tmp_path / "no-kb.json"),
    )


@pytest.fixture
def client(settings) -> TestClient:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def auth(client) -> dict:
    """Заголовок новой демо-сессии."""
    token = client.post("/api/auth/demo").json()["token"]
    return {"Authorization": f"Bearer {token}"}
