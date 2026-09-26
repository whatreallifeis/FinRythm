"""Проверочные примеры из docs/check_examples.md: числа посчитаны вручную на 26.09.2026."""

import pytest

pytestmark = pytest.mark.e2e

RENT_1ST = {"date": "2026-09-01", "amount": -12000, "category": "rent", "merchant": "Аренда комнаты"}


def _user(client) -> dict:
    return {"Authorization": f"Bearer {client.post('/api/auth/demo').json()['token']}"}


def _setup(client, balance: int, incomes: list[dict], rows: list[dict]) -> dict:
    headers = _user(client)
    assert (
        client.put("/api/profile", headers=headers, json={"balance": balance, "incomes": incomes}).status_code
        == 200
    )
    if rows:
        imported = client.post("/api/transactions/import", headers=headers, json={"rows": rows}).json()
        assert imported["imported"] == len(rows), imported
    return headers


def test_case1_deficit(client, demo_date):
    """Баланс 5 000, аренда 12 000 1-го, стипендия 8 000 5-го: 4 красных дня, лимит 0."""
    h = _setup(client, 5000, [{"title": "Стипендия", "amount": 8000, "dayOfMonth": 5}], [RENT_1ST])

    runway = client.get("/api/analysis/runway", headers=h).json()["result"]
    assert runway["todaySafeSpend"] == 0
    assert runway["lowestBalance"] == -7000
    assert runway["redDays"] == 4
    red = [d["date"] for d in runway["days"] if d["status"] == "shortfall"]
    assert red == ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
    assert runway["days"][-1] == {
        "date": "2026-10-05",
        "events": [{"title": "Стипендия", "amount": 8000}],
        "balance": 1000,
        "status": "tight",
    }

    forecast = client.get("/api/analysis/forecast", headers=h).json()["result"]
    assert (forecast["projectedBalance"], forecast["safeDailySpend"], forecast["verdict"]) == (
        5000,
        0,
        "shortfall",
    )

    impulse = client.post("/api/analysis/impulse", headers=h, json={"amount": 500}).json()["result"]
    assert (impulse["verdict"], impulse["lowestBalanceAfter"], impulse["waitUntil"]) == (
        "shortfall",
        -7500,
        None,
    )


def test_case2_no_incomes(client, demo_date):
    """Баланс 6 000, аренда 5 000 10-го, поступлений нет."""
    rent = {"date": "2026-09-10", "amount": -5000, "category": "rent", "merchant": "Аренда комнаты"}
    h = _setup(client, 6000, [], [rent])

    runway = client.get("/api/analysis/runway", headers=h).json()
    assert runway["dataQuality"]["sufficient"] is False
    assert runway["dataQuality"]["missing"] == ["хотя бы одно регулярное поступление с днём месяца"]

    body = client.post("/api/analysis/impulse", headers=h, json={"amount": 2000}).json()
    r = body["result"]
    assert r["todaySafeSpendBefore"] == 71  # (6 000 − 5 000) / 14
    assert (r["verdict"], r["lowestBalanceAfter"], r["redDaysAfter"]) == ("shortfall", -1000, 1)
    assert any("Поступлений в профиле нет" in a for a in body["assumptions"])


def test_case3_purchase_bigger_than_balance(client, demo_user, demo_date):
    r = client.post("/api/analysis/impulse", headers=demo_user, json={"amount": 20000}).json()["result"]

    assert r["daysAfter"][0]["balance"] == -1570
    assert r["lowestBalanceAfter"] == -15718
    assert r["redDaysAfter"] == 14
    assert r["verdict"] == "shortfall"
    assert r["waitUntil"]["title"] == "Подработка" and r["waitUntil"]["date"] == "2026-10-10"
    assert r["goalImpact"] == {"goalTitle": "Ноутбук для учёбы", "delayDays": 48}


def test_case4_income_today(client, demo_date):
    """Зарплата 26-го уже в балансе 30 000; следующая 26.10; аренда 12 000 1-го."""
    h = _setup(client, 30000, [{"title": "Зарплата", "amount": 20000, "dayOfMonth": 26}], [RENT_1ST])
    body = client.get("/api/analysis/runway", headers=h).json()
    r = body["result"]

    assert r["nextIncome"] == {"date": "2026-10-26", "title": "Зарплата", "amount": 20000, "daysUntil": 30}
    assert r["todaySafeSpend"] == 600  # (30 000 − 12 000) / 30
    assert r["lowestBalance"] == 18000
    assert r["redDays"] == 0
    assert any("«Зарплата» сегодня" in a for a in body["assumptions"])


def test_case5_goals(client, demo_date):
    h = _user(client)
    drafts = {
        "bike": {"title": "Велосипед", "targetAmount": 30000, "savedAmount": 6000, "deadline": "2026-12-25"},
        "cushion": {"title": "Подушка", "targetAmount": 20000, "savedAmount": 2000, "deadline": None},
        "headphones": {"title": "Наушники", "targetAmount": 10000, "savedAmount": 10000, "deadline": None},
    }
    ids = {
        key: client.post("/api/goals", headers=h, json=draft).json()["id"] for key, draft in drafts.items()
    }
    plan = {key: client.get(f"/api/goals/{goal_id}/plan", headers=h).json() for key, goal_id in ids.items()}

    bike = plan["bike"]["result"]
    assert (bike["monthlyPace"], bike["etaMonths"], bike["etaDate"]) == (8000, 3, "2026-12-25")
    assert plan["cushion"]["dataQuality"]["sufficient"] is False
    assert plan["cushion"]["dataQuality"]["missing"] == ["срок, к которому нужна сумма"]
    done = plan["headphones"]
    assert done["dataQuality"]["sufficient"] is True
    assert (done["result"]["monthlyPace"], done["result"]["etaMonths"]) == (0, 0)
