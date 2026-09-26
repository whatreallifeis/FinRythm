"""Проверки форм ответов по frontend/src/shared/api/types.ts (ветка front)."""

import re

CATEGORIES = {"food", "transport", "subscriptions", "entertainment", "health", "education", "rent", "other"}
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)


def is_number(value) -> bool:
    """Деньги в JSON — числа, не строки (types.ts)."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def is_date(value) -> bool:
    return isinstance(value, str) and bool(ISO_DATE.match(value))


def check_explained(body: dict) -> dict:
    """Обёртка Explained<T>; возвращает result."""
    assert set(body) == {"result", "assumptions", "calculation", "sources", "limitations", "dataQuality"}, (
        body
    )
    assert all(isinstance(a, str) for a in body["assumptions"])
    for step in body["calculation"]:
        assert set(step) == {"label", "formula", "value"}
        assert is_number(step["value"]), step
    for source in body["sources"]:
        assert set(source) == {"title", "url"}
    assert body["limitations"], "ограничения должны быть всегда"
    quality = body["dataQuality"]
    assert set(quality) == {"sufficient", "missing", "coverageDays"}
    assert isinstance(quality["coverageDays"], int) and quality["coverageDays"] >= 0
    if quality["sufficient"]:
        assert quality["missing"] == []
    else:
        assert quality["missing"], "при нехватке данных нужно сказать, чего не хватает"
        assert all(CYRILLIC.search(m) for m in quality["missing"]), quality["missing"]
    return body["result"]


def check_income(item: dict | None) -> None:
    if item is None:
        return
    assert set(item) == {"date", "title", "amount", "daysUntil"}
    assert is_date(item["date"]) and is_number(item["amount"]) and isinstance(item["daysUntil"], int)


def check_days(days: list[dict]) -> None:
    for day in days:
        assert set(day) == {"date", "events", "balance", "status"}
        assert is_date(day["date"]) and is_number(day["balance"])
        assert day["status"] in {"ok", "tight", "shortfall"}
        for event in day["events"]:
            assert set(event) == {"title", "amount"} and is_number(event["amount"])


def check_runway(r: dict) -> None:
    assert set(r) == {"horizonTo", "nextIncome", "todaySafeSpend", "lowestBalance", "redDays", "days"}
    assert is_date(r["horizonTo"])
    check_income(r["nextIncome"])
    assert is_number(r["todaySafeSpend"]) and is_number(r["lowestBalance"]) and isinstance(r["redDays"], int)
    check_days(r["days"])


def check_impulse(r: dict) -> None:
    assert set(r) == {
        "amount",
        "verdict",
        "hint",
        "todaySafeSpendBefore",
        "todaySafeSpendAfter",
        "redDaysBefore",
        "redDaysAfter",
        "lowestBalanceAfter",
        "waitUntil",
        "goalImpact",
        "daysAfter",
    }
    assert r["verdict"] in {"ok", "wait", "shortfall"}
    assert isinstance(r["hint"], str)
    for key in ("amount", "todaySafeSpendBefore", "todaySafeSpendAfter", "lowestBalanceAfter"):
        assert is_number(r[key]), key
    check_income(r["waitUntil"])
    if r["goalImpact"] is not None:
        assert set(r["goalImpact"]) == {"goalTitle", "delayDays"}
    check_days(r["daysAfter"])


def check_forecast(r: dict) -> None:
    assert set(r) == {
        "daysLeft",
        "expectedIncome",
        "plannedExpenses",
        "projectedBalance",
        "safeDailySpend",
        "verdict",
    }
    assert isinstance(r["daysLeft"], int)
    assert r["verdict"] in {"ok", "tight", "shortfall"}
    for key in ("expectedIncome", "plannedExpenses", "projectedBalance", "safeDailySpend"):
        assert is_number(r[key]), key


def check_overview(r: dict) -> None:
    assert set(r) == {
        "periodFrom",
        "periodTo",
        "totalIncome",
        "totalExpense",
        "recurringTotal",
        "byCategory",
        "anomalies",
    }
    assert is_date(r["periodFrom"]) and is_date(r["periodTo"])
    for s in r["byCategory"]:
        assert set(s) == {"category", "amount", "share", "deltaPercent"}
        assert s["category"] in CATEGORIES
        assert 0 <= s["share"] <= 1
        assert s["deltaPercent"] is None or isinstance(s["deltaPercent"], int)
    for a in r["anomalies"]:
        assert set(a) == {"transactionId", "reason"}


def check_goal_plan(r: dict) -> None:
    assert set(r) == {"goalId", "monthlyPace", "etaMonths", "etaDate", "blockers"}
    assert is_number(r["monthlyPace"])
    assert r["etaDate"] is None or is_date(r["etaDate"])
    for b in r["blockers"]:
        assert set(b) == {"category", "amount", "hint"} and b["category"] in CATEGORIES


def check_error(response, status: int, code: str) -> str:
    """Единый формат ошибок {"error": {code, message, field}} с русским текстом."""
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code
    assert CYRILLIC.search(error["message"]), error
    return error["message"]
