"""S12: сквозной сценарий фронтенда — вход → демо-набор → аналитика → покупка → цели → помощник.

Точные числа — демо 26.09.2026 (handoff.md ветки front, эталон backend/tests/core/test_front_calc.py).
"""

import pytest
from e2e_helpers import (
    check_error,
    check_explained,
    check_forecast,
    check_goal_plan,
    check_impulse,
    check_overview,
    check_runway,
    is_date,
    is_number,
)

pytestmark = pytest.mark.e2e

SCENARIOS = {
    "expenses": "Куда уходят мои деньги?",
    "budget": "Хватит ли мне до стипендии?",
    "glossary": "Что такое инфляция?",
    "impulse": "Могу купить наушники за 14 900 ₽?",
    "free": "Как мне начать откладывать?",
}


def _plain(text: str) -> str:
    return text.replace(" ", " ")


# ---------------------------------------------------------------- данные пользователя


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"


def test_demo_seed_fills_profile_and_transactions(client, demo_user):
    profile = client.get("/api/profile", headers=demo_user).json()
    transactions = client.get("/api/transactions", headers=demo_user).json()

    assert profile["balance"] == 18430
    assert {(i["title"], i["amount"], i["dayOfMonth"]) for i in profile["incomes"]} == {
        ("Стипендия", 8000, 5),
        ("Подработка", 25000, 10),
    }
    assert [g["id"] for g in profile["goals"]] == ["g-1", "g-2"]
    assert profile["goals"][1]["deadline"] is None
    assert len(transactions) == 25
    dates = [t["date"] for t in transactions]
    assert dates == sorted(dates, reverse=True), "новые операции сверху"
    for t in transactions:
        assert set(t) == {"id", "date", "amount", "category", "merchant", "isRecurring"}
        assert is_date(t["date"]) and is_number(t["amount"])


def test_every_analysis_endpoint_answers_on_demo(client, demo_user):
    checks = {
        "/api/analysis/overview": check_overview,
        "/api/analysis/forecast": check_forecast,
        "/api/analysis/runway": check_runway,
    }
    for path, check in checks.items():
        response = client.get(path, headers=demo_user)
        assert response.status_code == 200, (path, response.text)
        body = response.json()
        check(check_explained(body))
        assert body["dataQuality"]["sufficient"] is True, path
        assert body["calculation"], path
    impulse = client.post("/api/analysis/impulse", headers=demo_user, json={"amount": 500})
    check_impulse(check_explained(impulse.json()))


# ---------------------------------------------------------------- числа демо-сценария


def test_demo_runway_numbers(client, demo_user, demo_date):
    body = client.get("/api/analysis/runway", headers=demo_user).json()
    r = body["result"]

    assert r["nextIncome"] == {"date": "2026-10-05", "title": "Стипендия", "amount": 8000, "daysUntil": 9}
    assert r["todaySafeSpend"] == 475
    assert r["lowestBalance"] == 4282
    assert r["redDays"] == 0
    assert r["horizonTo"] == "2026-10-17"
    assert len(r["days"]) == 22
    assert body["dataQuality"]["coverageDays"] == 57


@pytest.mark.parametrize(
    ("amount", "verdict", "after", "lowest", "wait", "delay"),
    [
        (14900, "shortfall", 0, -10618, "Подработка", 36),
        (3000, "wait", 142, 1282, "Стипендия", 8),
        (500, "ok", 420, 3782, None, 2),
    ],
)
def test_demo_impulse_numbers(client, demo_user, demo_date, amount, verdict, after, lowest, wait, delay):
    r = client.post("/api/analysis/impulse", headers=demo_user, json={"amount": amount}).json()["result"]

    assert r["amount"] == amount
    assert r["verdict"] == verdict
    assert r["todaySafeSpendBefore"] == 475
    assert r["todaySafeSpendAfter"] == after
    assert r["lowestBalanceAfter"] == lowest
    assert (r["waitUntil"] or {}).get("title") == wait
    assert r["goalImpact"] == {"goalTitle": "Ноутбук для учёбы", "delayDays": delay}


def test_limit_and_purchase_use_one_calendar(client, demo_user):
    runway = client.get("/api/analysis/runway", headers=demo_user).json()["result"]
    impulse = client.post("/api/analysis/impulse", headers=demo_user, json={"amount": 1000}).json()["result"]

    assert impulse["todaySafeSpendBefore"] == runway["todaySafeSpend"]
    assert [d["date"] for d in impulse["daysAfter"]] == [d["date"] for d in runway["days"]]


def test_demo_forecast_numbers(client, demo_user, demo_date):
    r = client.get("/api/analysis/forecast", headers=demo_user).json()["result"]

    assert r == {
        "daysLeft": 4,
        "expectedIncome": 0,
        "plannedExpenses": 0,
        "projectedBalance": 18430,
        "safeDailySpend": 475,  # не больше лимита календаря: аренда 1 октября (issue #12)
        "verdict": "tight",
    }


def test_demo_overview_numbers(client, demo_user, demo_date):
    r = client.get("/api/analysis/overview", headers=demo_user).json()["result"]

    assert (r["periodFrom"], r["periodTo"]) == ("2026-09-01", "2026-09-26")
    assert (r["totalIncome"], r["totalExpense"], r["recurringTotal"]) == (33000, 41928, 14738)
    assert [s["category"] for s in r["byCategory"]][:3] == ["entertainment", "rent", "food"]
    assert r["byCategory"][0] == {
        "category": "entertainment",
        "amount": 16540,
        "share": 0.3945,
        "deltaPercent": 934,
    }
    assert 0.99 <= sum(s["share"] for s in r["byCategory"]) <= 1.01
    assert [a["transactionId"] for a in r["anomalies"]] == ["t-911"]


# ---------------------------------------------------------------- цели


def test_demo_goal_plans(client, demo_user, demo_date):
    laptop = client.get("/api/goals/g-1/plan", headers=demo_user).json()
    cushion = client.get("/api/goals/g-2/plan", headers=demo_user).json()

    r = check_explained(laptop)
    check_goal_plan(r)
    assert (r["monthlyPace"], r["etaMonths"], r["etaDate"]) == (12657, 5, "2027-02-01")
    assert [b["category"] for b in r["blockers"]] == ["entertainment", "food"]
    check_goal_plan(check_explained(cushion))
    assert cushion["dataQuality"]["sufficient"] is False
    assert cushion["dataQuality"]["missing"] == ["срок, к которому нужна сумма"]


def test_goal_lifecycle(client, demo_user):
    draft = {"title": "Велосипед", "targetAmount": 30000, "savedAmount": 5000, "deadline": "2027-06-01"}
    created = client.post("/api/goals", headers=demo_user, json=draft)
    assert created.status_code == 201, created.text
    goal = created.json()
    assert {k: goal[k] for k in draft} == draft
    goal_id = goal["id"]

    plan = client.get(f"/api/goals/{goal_id}/plan", headers=demo_user).json()
    check_goal_plan(check_explained(plan))
    assert plan["result"]["goalId"] == goal_id
    assert plan["result"]["monthlyPace"] > 0

    done = client.patch(f"/api/goals/{goal_id}", headers=demo_user, json={**draft, "savedAmount": 30000})
    assert done.json()["savedAmount"] == 30000
    reached = client.get(f"/api/goals/{goal_id}/plan", headers=demo_user).json()
    assert reached["dataQuality"]["sufficient"] is True
    assert (reached["result"]["monthlyPace"], reached["result"]["etaMonths"]) == (0, 0)

    assert client.delete(f"/api/goals/{goal_id}", headers=demo_user).status_code == 204
    goals = client.get("/api/profile", headers=demo_user).json()["goals"]
    assert goal_id not in {g["id"] for g in goals}
    assert check_error(client.get(f"/api/goals/{goal_id}/plan", headers=demo_user), 404, "not_found") == (
        "Цель не найдена."
    )


# ---------------------------------------------------------------- помощник


@pytest.mark.parametrize("scenario_id", list(SCENARIOS))
def test_ask_every_scenario(client, demo_user, scenario_id):
    response = client.post(
        "/api/ask", headers=demo_user, json={"question": SCENARIOS[scenario_id], "scenarioId": scenario_id}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    result = check_explained(body)
    assert set(result) == {"text"} and isinstance(result["text"], str)
    if body["dataQuality"]["sufficient"]:
        assert result["text"].strip()


def test_ask_numbers_come_from_core(client, demo_user, demo_date):
    """Числа в ответе помощника — те же, что на экранах: их считает core, а не модель."""
    budget = client.post(
        "/api/ask", headers=demo_user, json={"question": SCENARIOS["budget"], "scenarioId": "budget"}
    ).json()
    impulse = client.post(
        "/api/ask", headers=demo_user, json={"question": SCENARIOS["impulse"], "scenarioId": "impulse"}
    ).json()

    assert "475 ₽" in _plain(budget["result"]["text"])
    text = _plain(impulse["result"]["text"])
    assert "14 900 ₽" in text and "Подработка" in text
    assert 475 in [step["value"] for step in impulse["calculation"]]


def test_ask_without_data_says_what_is_missing(client, new_user):
    body = client.post(
        "/api/ask", headers=new_user, json={"question": SCENARIOS["budget"], "scenarioId": "budget"}
    ).json()

    check_explained(body)
    assert body["dataQuality"]["sufficient"] is False
