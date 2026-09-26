"""SF3: граничные случаи расчётов нового API."""

import datetime as dt
from decimal import Decimal

import pytest
from app.core import (
    DEMO_AS_OF,
    build_forecast,
    build_goal_plan,
    build_overview,
    build_runway,
    check_impulse,
    load_demo_state,
)
from app.core.runway_calendar import next_on_day
from app.models import IncomeRule, Operation, SavingGoal, UserState

D = Decimal


def _rent(day: int = 10, amount: str = "-5000") -> Operation:
    return Operation(
        id="r",
        date=dt.date(2026, 9, day),
        amount=amount,
        category="rent",
        merchant="Аренда",
        is_recurring=True,
    )


@pytest.mark.parametrize(
    ("as_of", "day", "expected"),
    [
        (dt.date(2026, 9, 26), 5, dt.date(2026, 10, 5)),
        (dt.date(2026, 9, 5), 5, dt.date(2026, 10, 5)),  # сегодня — уже прошло, следующее через месяц
        (dt.date(2026, 9, 4), 5, dt.date(2026, 9, 5)),
        (dt.date(2026, 1, 31), 31, dt.date(2026, 2, 28)),  # 31-е в феврале — последний день
        (dt.date(2026, 12, 20), 10, dt.date(2027, 1, 10)),
    ],
)
def test_next_on_day(as_of, day, expected):
    assert next_on_day(as_of, day) == expected


# ---------------------------------------------------------------- нехватка данных


def test_no_balance_everywhere_asks_for_it():
    state = load_demo_state().model_copy(update={"balance": None})

    for e in (
        build_runway(state, DEMO_AS_OF),
        check_impulse(state, D("500"), DEMO_AS_OF),
        build_forecast(state, DEMO_AS_OF),
    ):
        assert e.data_quality.sufficient is False
        assert "текущий баланс" in e.data_quality.missing
        assert e.data_quality.coverage_days == 57


def test_runway_without_incomes_is_insufficient():
    state = UserState(balance=D("6000"), transactions=[_rent()])
    e = build_runway(state, DEMO_AS_OF)

    assert e.data_quality.sufficient is False
    assert e.data_quality.missing == ["хотя бы одно регулярное поступление с днём месяца"]
    assert e.result["days"] == []
    assert e.result["todaySafeSpend"] == 0


def test_empty_state():
    state = UserState()
    runway = build_runway(state, DEMO_AS_OF)
    overview = build_overview(state, DEMO_AS_OF)

    assert runway.data_quality.missing == [
        "текущий баланс",
        "хотя бы одно регулярное поступление с днём месяца",
    ]
    assert overview.data_quality.sufficient is False
    assert overview.data_quality.missing == ["операции хотя бы за один месяц"]
    assert overview.data_quality.coverage_days == 0
    assert overview.result["totalExpense"] == 0
    assert overview.result["byCategory"] == []


def test_overview_without_current_month():
    state = UserState(
        transactions=[Operation(id="a", date=dt.date(2026, 8, 3), amount="-100", merchant="Кафе")]
    )
    e = build_overview(state, DEMO_AS_OF)

    assert e.data_quality.sufficient is False
    assert e.data_quality.missing == ["операции за текущий месяц"]
    assert e.data_quality.coverage_days == 55


# ---------------------------------------------------------------- баланс 0, покупка больше баланса


def test_zero_balance():
    state = load_demo_state().model_copy(update={"balance": D("0")})
    r = build_runway(state, DEMO_AS_OF).result

    assert r["todaySafeSpend"] == 0
    assert r["days"][0]["status"] == "tight"
    assert r["lowestBalance"] == D("-14148")
    assert r["redDays"] == 9  # с 1 по 9 октября, до подработки


def test_purchase_bigger_than_balance():
    state = load_demo_state()
    r = check_impulse(state, D("20000"), DEMO_AS_OF).result

    assert r["verdict"] == "shortfall"
    assert r["daysAfter"][0]["balance"] == D("-1570")
    assert r["daysAfter"][0]["status"] == "shortfall"
    assert r["todaySafeSpendAfter"] == 0
    assert r["waitUntil"]["title"] == "Подработка"


def test_impulse_rejects_non_positive_amount():
    with pytest.raises(ValueError):
        check_impulse(load_demo_state(), D("0"), DEMO_AS_OF)


# ---------------------------------------------------------------- поступления


def test_income_today_counts_as_received():
    """5 октября стипендия уже в балансе: ближайшее поступление — подработка 10 октября."""
    as_of = dt.date(2026, 10, 5)
    e = build_runway(load_demo_state(), as_of)
    r = e.result

    assert r["nextIncome"]["title"] == "Подработка"
    assert r["nextIncome"]["daysUntil"] == 5
    assert r["todaySafeSpend"] == D("3686")  # 18 430 / 5, платежей до 10-го нет
    assert any("«Стипендия» сегодня" in a for a in e.assumptions)
    stipend = [d["date"] for d in r["days"] for ev in d["events"] if ev["title"] == "Стипендия"]
    assert stipend == ["2026-11-05"]


def test_without_income_last_bill_is_reserved():
    """В ветке front платёж в последний день горизонта не резервировался: лимит 428 ₽ вместо 71 ₽."""
    state = UserState(balance=D("6000"), transactions=[_rent()])
    r = check_impulse(state, D("2000"), DEMO_AS_OF).result

    # (6 000 − 5 000) / 14 дней до 10 октября
    assert r["todaySafeSpendBefore"] == D("71")
    assert r["verdict"] == "shortfall"
    assert r["waitUntil"] is None
    assert r["hint"].startswith("Сейчас не влезет")


def test_forecast_without_incomes_reserves_next_month_bills():
    state = UserState(balance=D("20000"), transactions=[_rent(day=1, amount="-12000")])
    r = build_forecast(state, DEMO_AS_OF).result

    assert r["plannedExpenses"] == 0
    assert r["projectedBalance"] == D("20000")
    assert r["safeDailySpend"] == D("2000")  # (20 000 − 12 000 аренда 1 октября) / 4


def test_forecast_never_exceeds_runway_limit():
    state = load_demo_state()
    for offset in range(0, 40):
        as_of = dt.date(2026, 9, 1) + dt.timedelta(days=offset)
        forecast = build_forecast(state, as_of).result["safeDailySpend"]
        runway = build_runway(state, as_of).result["todaySafeSpend"]
        assert forecast <= runway, as_of


def test_forecast_shortfall_when_bills_exceed_balance():
    state = UserState(
        balance=D("3000"),
        incomes=[IncomeRule(id="i", title="Стипендия", amount="8000", day_of_month=5)],
        transactions=[_rent(day=1, amount="-12000")],
    )
    r = build_forecast(state, DEMO_AS_OF).result

    assert r["verdict"] == "shortfall"
    assert r["safeDailySpend"] == 0


# ---------------------------------------------------------------- цели


def _goal_state(**goal) -> UserState:
    return UserState(
        balance=D("1000"), goals=[SavingGoal(id="g", title="Цель", target_amount="1000", **goal)]
    )


@pytest.mark.parametrize("deadline", [None, dt.date(2026, 1, 1), dt.date(2027, 1, 1)])
def test_goal_already_saved(deadline):
    e = build_goal_plan(_goal_state(saved_amount="1000", deadline=deadline), "g", DEMO_AS_OF)

    assert e.data_quality.sufficient is True
    assert e.result["monthlyPace"] == 0
    assert e.result["etaMonths"] == 0
    assert e.result["etaDate"] == "2026-09-26"


@pytest.mark.parametrize("deadline", [dt.date(2026, 9, 26), dt.date(2026, 1, 1)])
def test_goal_deadline_passed(deadline):
    e = build_goal_plan(_goal_state(saved_amount="100", deadline=deadline), "g", DEMO_AS_OF)

    assert e.data_quality.sufficient is False
    assert e.data_quality.missing == ["срок в будущем: указанный срок уже наступил"]
    assert e.result["etaDate"] is None


def test_goal_without_deadline():
    e = build_goal_plan(_goal_state(saved_amount="100"), "g", DEMO_AS_OF)

    assert e.data_quality.sufficient is False
    assert e.data_quality.missing == ["срок, к которому нужна сумма"]
    assert e.limitations == ["Без срока нельзя честно назвать дату, когда цель будет достигнута."]


def test_goal_impact_skips_goals_without_deadline():
    state = load_demo_state()
    state.goals = [g for g in state.goals if g.deadline is None]

    assert check_impulse(state, D("500"), DEMO_AS_OF).result["goalImpact"] is None


# ---------------------------------------------------------------- обзор


def test_overview_compares_with_same_days_of_previous_month():
    """Трата 28 августа не входит в сравнение для 26 сентября (в ветке front бралась бы)."""
    state = UserState(
        transactions=[
            Operation(id="a", date=dt.date(2026, 8, 10), amount="-100", category="food"),
            Operation(id="b", date=dt.date(2026, 8, 28), amount="-900", category="food"),
            Operation(id="c", date=dt.date(2026, 9, 10), amount="-150", category="food"),
        ]
    )
    r = build_overview(state, DEMO_AS_OF).result

    assert r["byCategory"][0]["deltaPercent"] == 50


def test_overview_last_day_of_month_compares_whole_months():
    state = UserState(
        transactions=[
            Operation(id="a", date=dt.date(2026, 8, 31), amount="-100", category="food"),
            Operation(id="b", date=dt.date(2026, 9, 30), amount="-200", category="food"),
        ]
    )
    r = build_overview(state, dt.date(2026, 9, 30)).result

    assert r["byCategory"][0]["deltaPercent"] == 100


def test_overview_shares_between_0_and_1():
    r = build_overview(load_demo_state(), DEMO_AS_OF).result

    assert all(D(0) <= s["share"] <= D(1) for s in r["byCategory"])
    assert D("0.99") <= sum(s["share"] for s in r["byCategory"]) <= D("1.01")
