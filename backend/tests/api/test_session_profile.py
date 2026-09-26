"""VF1: вход, профиль, операции, очистка, формат ошибок."""

import json
import time
from decimal import Decimal
from urllib.parse import urlencode

import pytest
from app.api.identity import TelegramAuthError, sign_init_data, user_id_for_telegram, verify_init_data
from app.models import Operation, UserState
from app.storage import Store, connect

from .conftest import BOT_TOKEN


def _init_data(user_id: int = 42, *, auth_date: int | None = None, token: str = BOT_TOKEN) -> str:
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAH-test",
        "user": json.dumps({"id": user_id, "first_name": "Аня", "last_name": "Тестова"}, ensure_ascii=False),
    }
    fields["hash"] = sign_init_data({k: v for k, v in fields.items()}, token)
    return urlencode(fields)


# ---------------------------------------------------------------- хранилище


def test_store_roundtrip_keeps_decimal(tmp_path):
    store = Store(connect(str(tmp_path / "db.sqlite3")))
    assert store.load("web:x") == UserState()
    state = UserState(
        balance=Decimal("18430.10"),
        transactions=[Operation(id="t-1", date="2026-09-20", amount=Decimal("-349.99"), category="food")],
    )
    store.save("web:x", state)
    loaded = store.load("web:x")
    assert loaded == state
    assert loaded.balance == Decimal("18430.10")
    store.clear("web:x")
    assert store.load("web:x") == UserState()


def test_store_sessions(tmp_path):
    store = Store(connect(str(tmp_path / "db.sqlite3")))
    session = store.create_session("web:abc", "Демо-режим", "demo")
    assert len(session.token) >= 32
    assert store.session(session.token) == session
    assert store.session("nope") is None


# ---------------------------------------------------------------- вход


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "fake"


def test_auth_demo_returns_session(client):
    body = client.post("/api/auth/demo").json()
    assert set(body) == {"token", "userId", "displayName", "mode"}
    assert body["userId"].startswith("web:")
    assert body["mode"] == "demo"
    assert body["displayName"] == "Демо-режим"


def test_two_demo_sessions_do_not_share_data(client):
    first = {"Authorization": f"Bearer {client.post('/api/auth/demo').json()['token']}"}
    second = {"Authorization": f"Bearer {client.post('/api/auth/demo').json()['token']}"}
    client.put("/api/profile", json={"balance": 500, "incomes": []}, headers=first)
    assert client.get("/api/profile", headers=second).json()["balance"] == 0


@pytest.mark.parametrize("header", [None, "Bearer", "Bearer wrong-token", "Basic abc"])
def test_protected_endpoint_requires_valid_token(client, header):
    headers = {"Authorization": header} if header else {}
    response = client.get("/api/profile", headers=headers)
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "unauthorized"
    assert "Войд" in error["message"] or "войти" in error["message"]


def test_auth_telegram_valid_init_data(client, settings):
    body = client.post("/api/auth/telegram", json={"initData": _init_data(42)}).json()
    assert body["mode"] == "telegram"
    assert body["displayName"] == "Аня Тестова"
    assert body["userId"] == user_id_for_telegram(42, settings.tg_id_salt)


def test_auth_telegram_same_user_gets_same_profile(client):
    first = client.post("/api/auth/telegram", json={"initData": _init_data(7)}).json()
    second = client.post("/api/auth/telegram", json={"initData": _init_data(7)}).json()
    assert first["userId"] == second["userId"]
    assert first["token"] != second["token"]
    first_auth = {"Authorization": f"Bearer {first['token']}"}
    client.put("/api/profile", json={"balance": 1234, "incomes": []}, headers=first_auth)
    profile = client.get("/api/profile", headers={"Authorization": f"Bearer {second['token']}"}).json()
    assert profile["balance"] == 1234


def test_auth_telegram_forged_hash_is_401(client):
    forged = _init_data(42, token="999:OTHER-BOT")
    response = client.post("/api/auth/telegram", json={"initData": forged})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Telegram не подтвердил вход."


def test_auth_telegram_not_configured_is_503(client):
    client.app.state.settings.telegram_bot_token = ""
    response = client.post("/api/auth/telegram", json={"initData": _init_data(42)})
    assert response.status_code == 503


def test_verify_init_data_expired():
    old = int(time.time()) - 2 * 86_400
    with pytest.raises(TelegramAuthError, match="устарела"):
        verify_init_data(_init_data(1, auth_date=old), BOT_TOKEN)


def test_verify_init_data_without_hash():
    with pytest.raises(TelegramAuthError, match="подпись"):
        verify_init_data("auth_date=1&user=%7B%7D", BOT_TOKEN)


# ---------------------------------------------------------------- профиль и данные


def test_empty_profile(client, auth):
    assert client.get("/api/profile", headers=auth).json() == {"balance": 0, "incomes": [], "goals": []}
    assert client.get("/api/transactions", headers=auth).json() == []


def test_put_profile_roundtrip(client, auth):
    body = {
        "balance": 18430.5,
        "incomes": [
            {"title": " Стипендия ", "amount": 8000, "dayOfMonth": 5},
            {"id": "i-job", "title": "Подработка", "amount": 25000, "dayOfMonth": 10},
        ],
    }
    saved = client.put("/api/profile", json=body, headers=auth).json()
    assert saved["balance"] == 18430.5
    assert saved["incomes"][0]["title"] == "Стипендия"
    assert saved["incomes"][0]["id"].startswith("i-")
    assert saved["incomes"][1] == {"id": "i-job", "title": "Подработка", "amount": 25000.0, "dayOfMonth": 10}
    assert client.get("/api/profile", headers=auth).json() == saved


@pytest.mark.parametrize(
    ("body", "field", "message"),
    [
        ({"balance": -1, "incomes": []}, "balance", "Значение должно быть не меньше 0"),
        ({"balance": "abc", "incomes": []}, "balance", "Нужно число"),
        ({"incomes": []}, "balance", "Обязательное поле"),
        (
            {"balance": 1, "incomes": [{"title": "Х", "amount": 1, "dayOfMonth": 32}]},
            "incomes.0.dayOfMonth",
            "Значение должно быть не больше 31",
        ),
    ],
)
def test_put_profile_validation_is_russian(client, auth, body, field, message):
    response = client.put("/api/profile", json=body, headers=auth)
    assert response.status_code == 422
    assert response.json() == {"error": {"code": "validation_error", "message": message, "field": field}}


def test_clear_dataset(client, auth):
    client.put("/api/profile", json={"balance": 100, "incomes": []}, headers=auth)
    assert client.delete("/api/dataset", headers=auth).status_code == 204
    assert client.get("/api/profile", headers=auth).json()["balance"] == 0


def test_unknown_path_error_format(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_folder_id_from_settings_reaches_openai_client(tmp_path, monkeypatch):
    """Алиса AI: ID каталога из .env должен попасть в окружение, откуда его берёт клиент openai."""
    from app.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    # пустое значение через monkeypatch — после теста переменная вернётся к исходному состоянию
    monkeypatch.setenv("OPENAI_PROJECT_ID", "")
    settings = Settings(
        _env_file=None,
        database_path=str(tmp_path / "db.sqlite3"),
        llm_provider="openai_compat",
        llm_base_url="https://ai.api.cloud.yandex.net/v1",
        llm_api_key="test-key",
        llm_model="gpt://b1gtestfolder/aliceai-llm",
        openai_project_id="b1gtestfolder",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["llm_provider"] == "openai_compat"
        assert client.app.state.llm is not None
        assert client.app.state.llm._client.project == "b1gtestfolder"
