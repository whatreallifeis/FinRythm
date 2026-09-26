"""Сквозные тесты: ходят в API только по HTTP и не импортируют код бэкенда.

Запуск: API_BASE_URL=http://localhost:8000 pytest -m e2e
Таймаут запроса — E2E_TIMEOUT секунд (по умолчанию 30; с моделью на CPU ответ помощника идёт до минуты).
Сервер — с LLM_PROVIDER=fake. Точные числа демо-сценария проверяются, только если сервер считает
на дату демо (APP_TODAY=2026-09-26); на другой дате проверяются формы ответов и правила.
"""

import os

import httpx
import pytest

DEMO_TODAY = "2026-09-26"


@pytest.fixture(scope="session")
def base_url() -> str:
    url = os.environ.get("API_BASE_URL")
    if not url:
        pytest.skip("API_BASE_URL не задан — e2e нужен запущенный API")
    return url.rstrip("/")


@pytest.fixture(scope="session")
def client(base_url: str):
    timeout = float(os.environ.get("E2E_TIMEOUT", "30"))
    with httpx.Client(base_url=base_url, timeout=timeout) as http:
        yield http


@pytest.fixture
def new_user(client: httpx.Client) -> dict:
    """Новая демо-сессия без данных: заголовки для запросов."""
    response = client.post("/api/auth/demo")
    assert response.status_code == 200, response.text
    session = response.json()
    assert session["mode"] == "demo"
    assert session["token"] and session["userId"]
    return {"Authorization": f"Bearer {session['token']}"}


@pytest.fixture
def demo_user(client: httpx.Client, new_user: dict) -> dict:
    """Новая сессия с демо-набором студента."""
    assert client.post("/api/demo/seed", headers=new_user).status_code == 204
    return new_user


@pytest.fixture
def server_today(client: httpx.Client, new_user: dict) -> str:
    """Дата, на которую считает сервер: конец периода обзора."""
    return client.get("/api/analysis/overview", headers=new_user).json()["result"]["periodTo"]


@pytest.fixture
def demo_date(server_today: str) -> None:
    if server_today != DEMO_TODAY:
        pytest.skip(
            f"точные числа демо — только при APP_TODAY={DEMO_TODAY}, сервер считает на {server_today}"
        )
