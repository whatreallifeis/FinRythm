"""SF3: расчёты нового API на демо-профиле 26.09.2026. Числа — эталон SF1 (API ветки front).

Отличия от эталона — исправления из issue #12: прогноз (475 ₽ и tight вместо 4 607 ₽ и ok)
и аномалии обзора (аренда t-901 не «разовая трата»).
"""

from decimal import Decimal

import pytest
from app.core import (
    DEMO_AS_OF,
    build_forecast,
    build_goal_plan,
    build_overview,
    build_runway,
    check_impulse,
    coverage_days,
    load_demo_state,
)
from app.core.explain import COMMON_LIMITS
from app.models import Explained

D = Decimal


@pytest.fixture
def demo():
    return load_demo_state()


def _days_with_events(days: list[dict]) -> list[tuple[str, Decimal, str, list]]:
    return [
        (d["date"], d["balance"], d["status"], [(e["title"], e["amount"]) for e in d["events"]])
        for d in days
        if d["events"]
    ]


def test_runway(demo):
    e = build_runway(demo, DEMO_AS_OF)
    r = e.result

    assert isinstance(e, Explained)
    assert e.data_quality.sufficient is True
    assert e.data_quality.coverage_days == 57
    assert e.limitations == COMMON_LIMITS
    assert r["horizonTo"] == "2026-10-17"
    assert r["nextIncome"] == {
        "date": "2026-10-05",
        "title": "Стипендия",
        "amount": D("8000"),
        "daysUntil": 9,
    }
    # (18 430 − 12 000 − 299 − 649 − 1 200) / 9 = 475,78 → 475
    assert r["todaySafeSpend"] == D("475")
    assert r["lowestBalance"] == D("4282")
    assert r["redDays"] == 0
    assert len(r["days"]) == 22
    assert r["days"][0] == {"date": "2026-09-26", "events": [], "balance": D("18430"), "status": "ok"}
    assert _days_with_events(r["days"]) == [
        ("2026-10-01", D("6430"), "ok", [("Аренда комнаты", D("-12000"))]),
        (
            "2026-10-02",
            D("5482"),
            "ok",
            [("Музыкальная подписка", D("-299")), ("Онлайн-кинотеатр", D("-649"))],
        ),
        ("2026-10-04", D("4282"), "ok", [("Проездной", D("-1200"))]),
        ("2026-10-05", D("12282"), "ok", [("Стипендия", D("8000"))]),
        ("2026-10-10", D("37282"), "ok", [("Подработка", D("25000"))]),
        ("2026-10-17", D("36692"), "ok", [("Мобильная связь", D("-590"))]),
    ]
    values = {s.label: s.value for s in e.calculation}
    assert values["Текущий баланс"] == D("18430")
    assert values["Дней до поступления"] == 9
    assert values["Обязательные платежи до поступления"] == D("14148")
    assert values["Можно тратить в день"] == D("475")
    assert values["Минимальный остаток"] == D("4282")


def test_impulse_14900_shortfall_wait_for_side_job(demo):
    """Сценарий handoff.md: покупка 14 900 ₽ даёт разрыв, стипендии не хватает — ждать подработку."""
    e = check_impulse(demo, D("14900"), DEMO_AS_OF)
    r = e.result

    assert e.data_quality.sufficient is True
    assert r["amount"] == D("14900")
    assert r["verdict"] == "shortfall"
    assert r["todaySafeSpendBefore"] == D("475")
    assert r["todaySafeSpendAfter"] == D("0")
    assert (r["redDaysBefore"], r["redDaysAfter"]) == (0, 9)
    assert r["lowestBalanceAfter"] == D("-10618")
    assert r["waitUntil"] == {
        "date": "2026-10-10",
        "title": "Подработка",
        "amount": D("25000"),
        "daysUntil": 14,
    }
    assert r["goalImpact"] == {"goalTitle": "Ноутбук для учёбы", "delayDays": 36}
    assert "Подождите «Подработка» 10 октября" in r["hint"]
    assert r["daysAfter"][0]["events"] == [{"title": "Покупка", "amount": D("-14900")}]
    assert r["daysAfter"][0]["balance"] == D("3530")
    red = [d["date"] for d in r["daysAfter"] if d["status"] == "shortfall"]
    assert red == [f"2026-10-0{i}" for i in range(1, 10)]


def test_impulse_3000_wait_for_stipend(demo):
    r = check_impulse(demo, D("3000"), DEMO_AS_OF).result

    assert r["verdict"] == "wait"
    assert (r["todaySafeSpendBefore"], r["todaySafeSpendAfter"]) == (D("475"), D("142"))
    assert (r["redDaysBefore"], r["redDaysAfter"]) == (0, 0)
    assert r["lowestBalanceAfter"] == D("1282")
    assert r["waitUntil"] == {"date": "2026-10-05", "title": "Стипендия", "amount": D("8000"), "daysUntil": 9}
    assert r["goalImpact"] == {"goalTitle": "Ноутбук для учёбы", "delayDays": 8}
    assert r["hint"].startswith("Лучше подождать до «Стипендия» 5 октября")


def test_impulse_500_ok(demo):
    r = check_impulse(demo, D("500"), DEMO_AS_OF).result

    assert r["verdict"] == "ok"
    assert (r["todaySafeSpendBefore"], r["todaySafeSpendAfter"]) == (D("475"), D("420"))
    assert r["lowestBalanceAfter"] == D("3782")
    assert r["waitUntil"] is None
    assert r["goalImpact"] == {"goalTitle": "Ноутбук для учёбы", "delayDays": 2}
    assert r["hint"] == "Покупка влезает: дневной лимит станет 420 ₽, обязательные платежи не пострадают."


def test_runway_and_impulse_share_one_calendar(demo):
    runway = build_runway(demo, DEMO_AS_OF).result
    for amount in ("500", "3000", "14900"):
        r = check_impulse(demo, D(amount), DEMO_AS_OF).result
        assert r["todaySafeSpendBefore"] == runway["todaySafeSpend"]
        assert [d["date"] for d in r["daysAfter"]] == [d["date"] for d in runway["days"]]


def test_forecast(demo):
    e = build_forecast(demo, DEMO_AS_OF)
    r = e.result

    assert e.data_quality.sufficient is True
    assert r["daysLeft"] == 4
    assert r["expectedIncome"] == D("0")
    assert r["plannedExpenses"] == D("0")
    assert r["projectedBalance"] == D("18430")
    # В ветке front 18 430 / 4 = 4 607 ₽ — это деньги на аренду 1 октября (issue #12).
    assert r["safeDailySpend"] == D("475")
    # Средний расход в сентябре 41 928 / 26 = 1 612 ₽ в день — больше лимита.
    assert r["verdict"] == "tight"
    values = {s.label: s.value for s in e.calculation}
    assert values["Отложить на платежи после месяца"] == D("14148")
    assert values["Можно тратить до конца месяца"] == D("1070")
    assert values["Лимит календаря до поступления"] == D("475")
    assert any("Аренда комнаты 12 000 ₽" in a for a in e.assumptions)


def test_overview(demo):
    e = build_overview(demo, DEMO_AS_OF)
    r = e.result

    assert e.data_quality.sufficient is True
    assert e.data_quality.coverage_days == 57
    assert (r["periodFrom"], r["periodTo"]) == ("2026-09-01", "2026-09-26")
    assert r["totalIncome"] == D("33000")
    assert r["totalExpense"] == D("41928")
    assert r["recurringTotal"] == D("14738")
    assert [(s["category"], s["amount"], s["share"], s["deltaPercent"]) for s in r["byCategory"]] == [
        ("entertainment", D("16540"), D("0.3945"), 934),
        ("rent", D("12000"), D("0.2862"), 0),
        ("food", D("6760"), D("0.1612"), 1),
        ("education", D("3200"), D("0.0763"), None),
        ("subscriptions", D("1538"), D("0.0367"), 414),
        ("transport", D("1440"), D("0.0343"), 20),
        ("health", D("450"), D("0.0107"), None),
    ]
    # Аренда t-901 регулярная — не «разовая трата» (issue #12).
    assert r["anomalies"] == [
        {"transactionId": "t-911", "reason": "Разовая трата 14 900 ₽ — это 36% расходов месяца"}
    ]
    values = {s.label: s.value for s in e.calculation}
    assert values["Доля регулярных, %"] == 35


def test_goal_plan_laptop(demo):
    e = build_goal_plan(demo, "g-1", DEMO_AS_OF)
    r = e.result

    assert e.data_quality.sufficient is True
    # 54 000 / (128 / 30) = 12 656,25 → 12 657
    assert r == {
        "goalId": "g-1",
        "monthlyPace": D("12657"),
        "etaMonths": 5,
        "etaDate": "2027-02-01",
        "blockers": [
            {
                "category": "entertainment",
                "amount": D("16540"),
                "hint": "Крупная трата на развлечения отодвигает цель. За месяц это около 1 мес. отчислений",
            },
            {
                "category": "food",
                "amount": D("6760"),
                "hint": "Еда вне дома — заметная часть необязательных расходов. "
                "За месяц это около 1 мес. отчислений",
            },
        ],
    }
    assert [s.value for s in e.calculation] == [D("54000"), D("12657")]


def test_goal_plan_cushion_without_deadline(demo):
    e = build_goal_plan(demo, "g-2", DEMO_AS_OF)

    assert e.data_quality.sufficient is False
    assert e.data_quality.missing == ["срок, к которому нужна сумма"]
    assert e.result == {
        "goalId": "g-2",
        "monthlyPace": D("0"),
        "etaMonths": None,
        "etaDate": None,
        "blockers": [],
    }


def test_goal_plan_unknown_goal(demo):
    assert build_goal_plan(demo, "g-404", DEMO_AS_OF) is None


def test_coverage_days(demo):
    assert coverage_days(demo.transactions, DEMO_AS_OF) == 57
    assert coverage_days([], DEMO_AS_OF) == 0


def test_explained_serializes(demo):
    """Результат — валидная модель Explained, которую API может отдать в JSON."""
    for e in (
        build_runway(demo, DEMO_AS_OF),
        check_impulse(demo, D("14900"), DEMO_AS_OF),
        build_forecast(demo, DEMO_AS_OF),
        build_overview(demo, DEMO_AS_OF),
        build_goal_plan(demo, "g-1", DEMO_AS_OF),
    ):
        restored = Explained.model_validate_json(e.model_dump_json())
        assert restored.data_quality == e.data_quality
        assert e.calculation and e.assumptions
