import datetime as dt
from decimal import Decimal

from app.core import calculate_runway, simulate
from app.models import Goal, Income, MandatoryPayment
from core_helpers import load_profile

NB = "\u00a0"


def codes(result) -> list[str]:
    return [a.code for a in result.assumptions]


def test_p1_formula_text(p1):
    assert calculate_runway(p1).formula_text == (
        f"(9{NB}800 − 1{NB}949 обяз. − 785,10 резерв − 1{NB}400 в цель) ÷ 14 дн. = 404 ₽ в день"
    )


def test_p2_deficit_formula_text(p2):
    assert calculate_runway(p2).formula_text == (
        f"2{NB}500 − 3{NB}200 обяз. = −700 ₽: не хватает 700 ₽ до поступления"
    )


def test_p1_mandatory_items_sorted_with_titles(p1):
    res = calculate_runway(p1)
    assert [(i.title, i.date) for i in res.mandatory_items] == [
        ("Мобильная связь", dt.date(2026, 10, 1)),
        ("Проездной", dt.date(2026, 10, 1)),
        ("Подписка на музыку", dt.date(2026, 10, 5)),
    ]
    assert sum(i.amount for i in res.mandatory_items) == res.mandatory_total
    assert res.next_income_title == "Стипендия"


def test_p1_assumptions(p1):
    res = calculate_runway(p1)
    assert codes(res) == ["expected_income_ignored", "reserve"]
    assert res.assumptions[0].text == f"Ожидаемые поступления (4{NB}000 ₽) не учтены, пока не придут"
    assert res.assumptions[1].text == "Отложен резерв 10% на непредвиденное"


def test_expected_income_counted_text(p1):
    res = calculate_runway(p1, k=Decimal("0.5"))
    assert "expected_income_counted" in codes(res)
    text = next(a.text for a in res.assumptions if a.code == "expected_income_counted")
    assert text == f"Учтено 50% ожидаемых поступлений (4{NB}000 ₽) — эти деньги ещё не пришли"
    assert f"+ 2{NB}000 ожид." in res.formula_text


def test_horizon_default(p3):
    res = calculate_runway(p3)
    assert res.horizon_is_assumed
    assert res.next_income_title is None
    assert res.assumptions[0].code == "horizon_default"
    assert res.assumptions[0].text == "Дата следующего поступления не указана — считаем на 30 дней"


def test_income_today():
    res = calculate_runway(load_profile("edge_income_today"))
    assert codes(res) == ["income_today", "no_payments", "reserve"]
    assert res.formula_text == f"(5{NB}000 − 500 резерв) ÷ 1 дн. = 4{NB}500 ₽ в день"


def test_goal_paused(p2):
    assert "goal_paused" in codes(calculate_runway(p2))


def test_goal_paused_partially(p1):
    poor = p1.model_copy(update={"balance": Decimal("3000")})
    res = calculate_runway(poor)
    assert res.status == "ok"
    assert res.goal_contribution < Decimal(1400)
    assert "goal_paused" in codes(res)


def test_delay_and_purchase_assumptions(p1):
    res = calculate_runway(p1, purchase=Decimal(3000), delay_days=7)
    assert "Сценарий: поступление задерживается на 7 дней" in [a.text for a in res.assumptions]
    assert f"Сценарий: покупка на 3{NB}000 ₽" in [a.text for a in res.assumptions]
    assert f"− 3{NB}000 покупка" in res.formula_text


def test_missing_balance():
    res = calculate_runway(load_profile("edge_empty"))
    assert res.status == "insufficient_data"
    assert res.missing[0].field == "balance"
    assert res.missing[0].message == "Укажите текущий баланс — без него лимит не посчитать"


def test_today_overrides_as_of(p1):
    res = calculate_runway(p1, today=dt.date(2026, 10, 3))
    assert res.as_of == dt.date(2026, 10, 3)
    assert res.horizon_days == 7


def test_weekly_and_once_payments(p1):
    p = p1.model_copy(
        update={
            "payments": [
                MandatoryPayment(
                    id="w", title="Еда", amount=Decimal(500), next_date=dt.date(2026, 9, 26), period="weekly"
                ),
                MandatoryPayment(
                    id="o", title="Взнос", amount=Decimal(100), next_date=dt.date(2026, 10, 2), period="once"
                ),
            ]
        }
    )
    res = calculate_runway(p)
    # 26.09, 03.10 (10.10 — уже вне окна) + разовый 02.10
    assert res.mandatory_total == Decimal("1100.00")


def test_monthly_payment_on_31st_does_not_crash(p1):
    p = p1.model_copy(
        update={
            "incomes": [
                Income(
                    id="i",
                    title="Стипендия",
                    amount=Decimal(3000),
                    date=dt.date(2027, 3, 1),
                    type="stipend",
                    confirmed=True,
                )
            ],
            "payments": [
                MandatoryPayment(id="m", title="Аренда", amount=Decimal(1), next_date=dt.date(2026, 10, 31))
            ],
            "goals": [],
        }
    )
    dates = [i.date for i in calculate_runway(p).mandatory_items]
    assert dates == [
        dt.date(2026, 10, 31),
        dt.date(2026, 11, 30),
        dt.date(2026, 12, 31),
        dt.date(2027, 1, 31),
        dt.date(2027, 2, 28),
    ]


def test_simulate_p1_purchase(p1):
    res = simulate(p1, purchase=Decimal(3000))
    assert res.before.daily_limit == Decimal(404)
    assert res.after.daily_limit == Decimal(211)
    assert res.delta_daily_limit == Decimal(-193)


def test_simulate_delay(p1):
    res = simulate(p1, delay_days=7)
    assert res.after.daily_limit == Decimal(236)
    assert res.delay_days == 7


def test_no_goals_no_goal_paused(p3):
    assert "goal_paused" not in codes(calculate_runway(p3))


def test_goal_zero_contribution(p1):
    p = p1.model_copy(
        update={"goals": [Goal(id="g", title="X", target_amount=Decimal(100), deadline=dt.date(2027, 1, 1))]}
    )
    res = calculate_runway(p)
    assert res.goal_contribution == Decimal("0.00")
    assert "goal_paused" not in codes(res)
