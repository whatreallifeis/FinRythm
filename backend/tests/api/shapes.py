"""Проверка форм ответов по схемам zod фронтенда (ветка front, frontend/src/shared/api/schemas.ts)."""

import re

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CATEGORIES = {"food", "transport", "subscriptions", "entertainment", "health", "education", "rent", "other"}


def _num(value) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def check_explained(body: dict, check_result) -> None:
    assert set(body) == {"result", "assumptions", "calculation", "sources", "limitations", "dataQuality"}
    assert all(isinstance(item, str) for item in body["assumptions"])
    assert all(isinstance(item, str) for item in body["limitations"])
    for step in body["calculation"]:
        assert set(step) == {"label", "formula", "value"}
        assert isinstance(step["label"], str) and isinstance(step["formula"], str) and _num(step["value"])
    for source in body["sources"]:
        assert set(source) == {"title", "url"} and source["url"].startswith("http")
    quality = body["dataQuality"]
    assert set(quality) == {"sufficient", "missing", "coverageDays"}
    assert isinstance(quality["sufficient"], bool)
    assert all(isinstance(item, str) for item in quality["missing"])
    assert _int(quality["coverageDays"]) and quality["coverageDays"] >= 0
    check_result(body["result"])


def _upcoming(value) -> None:
    if value is None:
        return
    assert set(value) == {"date", "title", "amount", "daysUntil"}
    assert _num(value["amount"]) and _int(value["daysUntil"]) and value["daysUntil"] >= 0


def _day(day: dict) -> None:
    assert set(day) == {"date", "events", "balance", "status"}
    assert ISO_DATE.match(day["date"]) and _num(day["balance"])
    assert day["status"] in {"ok", "tight", "shortfall"}
    for event in day["events"]:
        assert set(event) == {"title", "amount"} and _num(event["amount"])


def overview(result: dict) -> None:
    keys = {
        "periodFrom",
        "periodTo",
        "totalIncome",
        "totalExpense",
        "recurringTotal",
        "byCategory",
        "anomalies",
    }
    assert set(result) == keys
    for key in ("totalIncome", "totalExpense", "recurringTotal"):
        assert _num(result[key])
    for item in result["byCategory"]:
        assert set(item) == {"category", "amount", "share", "deltaPercent"}
        assert item["category"] in CATEGORIES and 0 <= item["share"] <= 1
    for item in result["anomalies"]:
        assert set(item) == {"transactionId", "reason"}


def forecast(result: dict) -> None:
    keys = {"daysLeft", "expectedIncome", "plannedExpenses", "projectedBalance", "safeDailySpend", "verdict"}
    assert set(result) == keys
    assert _int(result["daysLeft"]) and result["daysLeft"] >= 0
    assert result["verdict"] in {"ok", "tight", "shortfall"}


def runway(result: dict) -> None:
    assert set(result) == {"horizonTo", "nextIncome", "todaySafeSpend", "lowestBalance", "redDays", "days"}
    _upcoming(result["nextIncome"])
    assert _num(result["todaySafeSpend"]) and _num(result["lowestBalance"])
    assert _int(result["redDays"]) and result["redDays"] >= 0
    for day in result["days"]:
        _day(day)


def impulse(result: dict) -> None:
    keys = {
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
    assert set(result) == keys
    assert _num(result["amount"]) and result["amount"] > 0
    assert result["verdict"] in {"ok", "wait", "shortfall"}
    _upcoming(result["waitUntil"])
    if result["goalImpact"] is not None:
        assert set(result["goalImpact"]) == {"goalTitle", "delayDays"}
    for day in result["daysAfter"]:
        _day(day)


def goal_plan(result: dict) -> None:
    assert set(result) == {"goalId", "monthlyPace", "etaMonths", "etaDate", "blockers"}
    assert _num(result["monthlyPace"])
    for item in result["blockers"]:
        assert set(item) == {"category", "amount", "hint"} and item["category"] in CATEGORIES


def ask_answer(result: dict) -> None:
    assert set(result) == {"text"} and isinstance(result["text"], str) and result["text"]
