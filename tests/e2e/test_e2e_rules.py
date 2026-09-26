"""S12: правила API — вход, проверка ввода, нехватка данных, импорт, история, очистка."""

import pytest
from e2e_helpers import (
    check_error,
    check_explained,
    check_forecast,
    check_impulse,
    check_overview,
    check_runway,
)

pytestmark = pytest.mark.e2e

ANALYSIS = ["/api/analysis/overview", "/api/analysis/forecast", "/api/analysis/runway"]


# ---------------------------------------------------------------- вход


@pytest.mark.parametrize("path", [*ANALYSIS, "/api/profile", "/api/transactions", "/api/history"])
def test_requires_session(client, path):
    check_error(client.get(path), 401, "unauthorized")
    check_error(client.get(path, headers={"Authorization": "Bearer not-a-token"}), 401, "unauthorized")


def test_users_do_not_see_each_other(client, demo_user):
    other = {"Authorization": f"Bearer {client.post('/api/auth/demo').json()['token']}"}

    assert len(client.get("/api/transactions", headers=demo_user).json()) == 25
    assert client.get("/api/transactions", headers=other).json() == []


# ---------------------------------------------------------------- нехватка данных — не ошибка


def test_empty_user_gets_insufficient_not_invented_numbers(client, new_user):
    checks = dict(zip(ANALYSIS, (check_overview, check_forecast, check_runway), strict=True))
    for path, check in checks.items():
        response = client.get(path, headers=new_user)
        assert response.status_code == 200, path
        body = response.json()
        check(check_explained(body))
        assert body["dataQuality"]["sufficient"] is False, path

    runway = client.get("/api/analysis/runway", headers=new_user).json()
    assert "текущий баланс" in runway["dataQuality"]["missing"]
    assert runway["result"]["days"] == []
    impulse = client.post("/api/analysis/impulse", headers=new_user, json={"amount": 500}).json()
    check_impulse(check_explained(impulse))
    assert impulse["dataQuality"]["sufficient"] is False


def test_profile_without_incomes_asks_for_income(client, new_user):
    saved = client.put("/api/profile", headers=new_user, json={"balance": 5000, "incomes": []})
    assert saved.status_code == 200
    runway = client.get("/api/analysis/runway", headers=new_user).json()

    assert runway["dataQuality"]["sufficient"] is False
    assert runway["dataQuality"]["missing"] == ["хотя бы одно регулярное поступление с днём месяца"]


def test_profile_update_changes_the_calendar(client, new_user):
    profile = {"balance": 9000, "incomes": [{"title": "Стипендия", "amount": 8000, "dayOfMonth": 5}]}
    saved = client.put("/api/profile", headers=new_user, json=profile).json()
    assert saved["balance"] == 9000 and saved["incomes"][0]["id"]

    body = client.get("/api/analysis/runway", headers=new_user).json()
    r = check_explained(body)
    assert body["dataQuality"]["sufficient"] is True
    assert r["nextIncome"]["title"] == "Стипендия"
    assert r["todaySafeSpend"] == 9000 // r["nextIncome"]["daysUntil"]  # платежей нет


# ---------------------------------------------------------------- проверка ввода


@pytest.mark.parametrize("amount", [-100, 0, "сто"])
def test_impulse_rejects_bad_amount(client, demo_user, amount):
    check_error(
        client.post("/api/analysis/impulse", headers=demo_user, json={"amount": amount}),
        422,
        "validation_error",
    )


def test_negative_balance_rejected(client, new_user):
    response = client.put("/api/profile", headers=new_user, json={"balance": -1, "incomes": []})
    check_error(response, 422, "validation_error")


def test_goal_saved_above_target_rejected(client, demo_user):
    draft = {"title": "Цель", "targetAmount": 1000, "savedAmount": 2000, "deadline": None}
    message = check_error(client.post("/api/goals", headers=demo_user, json=draft), 422, "validation_error")
    assert "больше суммы цели" in message


def test_unknown_scenario_rejected(client, demo_user):
    response = client.post("/api/ask", headers=demo_user, json={"question": "Привет", "scenarioId": "stocks"})
    check_error(response, 422, "validation_error")


def test_unknown_goal_is_404(client, demo_user):
    check_error(client.get("/api/goals/g-404/plan", headers=demo_user), 404, "not_found")
    check_error(client.delete("/api/goals/g-404", headers=demo_user), 404, "not_found")


# ---------------------------------------------------------------- импорт


def test_import_rows(client, new_user, server_today):
    rows = [
        {"date": server_today, "amount": -540, "category": "food", "merchant": "Супермаркет"},
        {"date": server_today, "amount": -100, "category": "other", "merchant": "4276 1234 5678 9012"},
        {
            "date": server_today,
            "amount": -100,
            "category": "other",
            "merchant": "Перевод 4276 1234 5678 9012 от 12.09",
        },
        {"date": server_today, "amount": 0, "category": "food", "merchant": "Пусто"},
        {"date": "2999-01-01", "amount": -100, "category": "food", "merchant": "Из будущего"},
        {"date": server_today, "amount": -300, "category": "Кафе", "merchant": "Кофейня"},
        {"date": server_today, "amount": -540, "category": "food", "merchant": "супермаркет"},
    ]
    response = client.post("/api/transactions/import", headers=new_user, json={"rows": rows})
    assert response.status_code == 200, response.text
    body = response.json()

    assert set(body) == {"imported", "rejected", "warnings"}
    assert body["imported"] == 2
    assert [r["row"] for r in body["rejected"]] == [2, 3, 4, 5]
    assert all("карт" in r["message"] for r in body["rejected"][:2])
    assert any("Строка 6" in w for w in body["warnings"]), "неизвестная категория → другое"
    assert any("Строка 7" in w for w in body["warnings"]), "дубликат пропущен"
    ops = client.get("/api/transactions", headers=new_user).json()
    assert {(o["merchant"], o["category"]) for o in ops} == {("Супермаркет", "food"), ("Кофейня", "other")}
    assert not any("4276" in o["merchant"] for o in ops)

    again = client.post("/api/transactions/import", headers=new_user, json={"rows": rows[:1]}).json()
    assert again["imported"] == 0
    assert again["warnings"]


def test_import_bad_date_is_validation_error(client, new_user):
    rows = [{"date": "26.09.2026", "amount": -100, "category": "food", "merchant": "Кафе"}]
    check_error(
        client.post("/api/transactions/import", headers=new_user, json={"rows": rows}),
        422,
        "validation_error",
    )


def test_import_keeps_demo_calendar(client, demo_user, server_today):
    """Импорт не делает «Супермаркет» и «Доставку еды» обязательными платежами (issue #12)."""
    before = client.get("/api/analysis/runway", headers=demo_user).json()["result"]
    rows = [{"date": server_today, "amount": -250, "category": "food", "merchant": "Кофейня у дома"}]
    client.post("/api/transactions/import", headers=demo_user, json={"rows": rows})
    after = client.get("/api/analysis/runway", headers=demo_user).json()["result"]

    assert after["days"] == before["days"]
    titles = {e["title"] for d in after["days"] for e in d["events"]}
    assert not titles & {"Супермаркет", "Доставка еды", "Кинотеатр"}


# ---------------------------------------------------------------- история и очистка


def test_history_roundtrip(client, new_user):
    entry = {
        "id": "h-1",
        "scenarioId": "budget",
        "title": "Хватит ли до стипендии?",
        "createdAt": "2026-09-26T10:00:00Z",
        "messages": [{"role": "user", "text": "Хватит ли до стипендии?"}],
    }
    assert client.put("/api/history/h-1", headers=new_user, json=entry).status_code == 200
    assert client.get("/api/history", headers=new_user).json()[0]["id"] == "h-1"
    check_error(client.put("/api/history/h-2", headers=new_user, json=entry), 422, "validation_error")
    assert client.delete("/api/history", headers=new_user).status_code == 204
    assert client.get("/api/history", headers=new_user).json() == []


def test_seed_keeps_history_and_clear_removes_data(client, new_user):
    entry = {
        "id": "h-1",
        "scenarioId": "free",
        "title": "Вопрос",
        "createdAt": "2026-09-26T10:00:00Z",
        "messages": [],
    }
    client.put("/api/history/h-1", headers=new_user, json=entry)
    client.post("/api/demo/seed", headers=new_user)
    assert [h["id"] for h in client.get("/api/history", headers=new_user).json()] == ["h-1"]

    assert client.delete("/api/dataset", headers=new_user).status_code == 204
    assert client.get("/api/transactions", headers=new_user).json() == []
    overview = client.get("/api/analysis/overview", headers=new_user).json()
    assert overview["dataQuality"]["sufficient"] is False
