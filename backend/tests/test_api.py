import hashlib
import hmac
import json
import time
from datetime import date
from urllib.parse import urlencode

import pytest
from app.clock import set_today
from app.config import get_settings
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    get_settings.cache_clear()
    set_today(date(2026, 9, 26))
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
    set_today(None)
    get_settings.cache_clear()


def _login(client: TestClient) -> dict:
    response = client.post("/api/auth/demo")
    assert response.status_code == 200
    body = response.json()
    return {"Authorization": f"Bearer {body['token']}"}


def test_empty_profile_does_not_invent_numbers(client: TestClient):
    headers = _login(client)
    overview = client.get("/api/analysis/overview", headers=headers)
    assert overview.status_code == 200
    body = overview.json()
    assert body["dataQuality"]["sufficient"] is False
    assert body["dataQuality"]["missing"]
    assert body["result"]["totalExpense"] == 0


def test_demo_seed_explains_spending_and_purchase(client: TestClient):
    headers = _login(client)
    assert client.post("/api/demo/seed", headers=headers).status_code == 204

    overview = client.get("/api/analysis/overview", headers=headers).json()
    assert overview["dataQuality"]["sufficient"] is True
    assert overview["result"]["totalExpense"] > 0
    assert any(item["transactionId"] == "t-911" for item in overview["result"]["anomalies"])
    shares = sum(item["share"] for item in overview["result"]["byCategory"])
    assert 0.99 <= shares <= 1.01
    assert overview["calculation"]
    assert overview["limitations"]

    runway = client.get("/api/analysis/runway", headers=headers).json()
    assert runway["result"]["todaySafeSpend"] == 475
    assert runway["result"]["nextIncome"]["title"] == "Стипендия"

    impulse = client.post("/api/analysis/impulse", headers=headers, json={"amount": 14900}).json()
    assert impulse["result"]["verdict"] == "shortfall"
    assert impulse["result"]["waitUntil"]["title"] == "Подработка"
    assert impulse["dataQuality"]["sufficient"] is True

    plan = client.get("/api/goals/g-1/plan", headers=headers).json()
    assert plan["dataQuality"]["sufficient"] is True
    assert plan["result"]["monthlyPace"] > 0
    assert plan["result"]["etaDate"] == "2027-02-01"

    cushion = client.get("/api/goals/g-2/plan", headers=headers).json()
    assert cushion["dataQuality"]["sufficient"] is False
    assert cushion["dataQuality"]["missing"]


def test_import_rejects_card_and_accepts_a_real_row(client: TestClient):
    headers = _login(client)
    response = client.post(
        "/api/transactions/import",
        headers=headers,
        json={
            "rows": [
                {"date": "2026-09-27", "amount": -540, "category": "food", "merchant": "Супермаркет"},
                {
                    "date": "2026-09-27",
                    "amount": -100,
                    "category": "other",
                    "merchant": "4276 1234 5678 9012",
                },
                {"date": "2026-09-28", "amount": 0, "category": "food", "merchant": "Пусто"},
            ]
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 1
    assert len(body["rejected"]) == 2
    assert any("карт" in item["message"] for item in body["rejected"])


def test_assistant_refuses_crypto_and_explains_known_term(client: TestClient):
    headers = _login(client)
    client.post("/api/demo/seed", headers=headers)

    refused = client.post(
        "/api/ask",
        headers=headers,
        json={"question": "Вложи все мои деньги в крипту", "scenarioId": "free"},
    ).json()
    assert refused["dataQuality"]["sufficient"] is True
    assert "не разбираю" in refused["result"]["text"]
    assert refused["sources"][0]["url"].startswith("https://")

    term = client.post(
        "/api/ask",
        headers=headers,
        json={"question": "Что такое инфляция?", "scenarioId": "glossary"},
    ).json()
    assert term["dataQuality"]["sufficient"] is True
    assert term["sources"][0]["url"].startswith("https://www.cbr.ru/")

    unknown = client.post(
        "/api/ask",
        headers=headers,
        json={"question": "Что такое эскроу-счёт?", "scenarioId": "glossary"},
    ).json()
    assert unknown["dataQuality"]["sufficient"] is False


def test_analysis_requires_session(client: TestClient):
    assert client.get("/api/analysis/overview").status_code == 401


def test_telegram_login_checks_signature(client: TestClient, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    get_settings.cache_clear()
    user = json.dumps({"id": 42, "first_name": "Аня"}, ensure_ascii=False)
    fields = {"auth_date": str(int(time.time())), "query_id": "q", "user": user}
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", b"test-token", hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()

    ok = client.post("/api/auth/telegram", json={"initData": urlencode(fields)})
    assert ok.status_code == 200
    assert ok.json()["displayName"] == "Аня"
    assert ok.json()["mode"] == "telegram"

    fields["hash"] = "0" * 64
    bad = client.post("/api/auth/telegram", json={"initData": urlencode(fields)})
    assert bad.status_code == 401
