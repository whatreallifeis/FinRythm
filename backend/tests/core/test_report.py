"""Полная сводка по выписке: числа сходятся с экранами и между собой."""

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from app.core import build_report, build_runway, report_text
from app.ingest import state_from_csv
from app.models import AutopaymentRule, SavingGoal, UserState

AS_OF = dt.date(2026, 9, 26)
PRESETS = Path(__file__).resolve().parents[3] / "frontend" / "src" / "features" / "import" / "presets"


def preset(name: str, balance: str, goals: list[SavingGoal] | None = None) -> UserState:
    state, _ = state_from_csv((PRESETS / f"{name}.csv").read_text(encoding="utf-8"), Decimal(balance), AS_OF)
    return state.model_copy(update={"goals": goals or []})


@pytest.fixture
def worker() -> UserState:
    goal = SavingGoal(
        id="g-1", title="Отпуск", target_amount="45000", saved_amount="12000", deadline=dt.date(2027, 6, 1)
    )
    return preset("worker", "21000", [goal])


def test_months_income_expense_and_savings_rate(worker):
    august, september = build_report(worker, AS_OF)["months"]
    assert august["complete"] and not september["complete"]
    assert august["income"] == Decimal("46000.00")
    assert august["expense"] == Decimal("40758.05")
    assert august["net"] == Decimal("5241.95")
    assert august["savingsRatePct"] == Decimal("11.4")
    assert august["recurringExpense"] + august["oneOffExpense"] == august["expense"]


def test_categories_shares_add_up_and_large_purchase_found(worker):
    current = build_report(worker, AS_OF)["current"]
    total = sum(c["amount"] for c in current["categories"])
    assert total == current["expense"]
    assert abs(sum(c["sharePct"] for c in current["categories"]) - 100) <= Decimal("0.5")
    assert [item["merchant"] for item in current["large"]] == ["M.VIDEO Krasnoyarsk RU"]
    assert current["topMerchants"][0]["merchant"] == "M.VIDEO Krasnoyarsk RU"


def test_runway_numbers_are_the_same_as_on_the_calendar(worker):
    report = build_report(worker, AS_OF)
    calendar = build_runway(worker, AS_OF).result
    assert report["runway"]["todaySafeSpend"] == calendar["todaySafeSpend"] == Decimal(79)
    assert report["runway"]["lowestBalance"] == calendar["lowestBalance"]
    assert [p["title"] for p in report["runway"]["paymentsBeforeIncome"]][0].startswith("Внешний перевод")


def test_goal_pace_uses_last_full_month(worker):
    goal = build_report(worker, AS_OF)["goals"][0]
    assert goal["remaining"] == Decimal("33000.00")
    assert goal["freeMonthly"] == Decimal("5241.95")
    assert goal["etaMonthsAtCurrentPace"] == 7  # 33 000 / 5 241,95 → 6,3 → 7 месяцев
    assert goal["requiredMonthly"] is not None and goal["onTrack"]


def test_cash_gap_is_a_critical_risk():
    risks = build_report(preset("freelance", "2300"), AS_OF)["risks"]
    kinds = [r["kind"] for r in risks]
    assert kinds[0] == "cash_gap" and risks[0]["severity"] == "critical"
    assert "overspending" in kinds


def test_manual_autopayment_is_in_regular_payments_and_calendar():
    state = preset("student", "4092").model_copy(
        update={
            "autopayments": [
                AutopaymentRule(id="a-1", title="Спортзал", amount="2500", day_of_month=1, category="health")
            ]
        }
    )
    report = build_report(state, AS_OF)
    gym = next(p for p in report["regular"]["payments"] if p["title"] == "Спортзал")
    assert gym["source"] == "manual" and gym["annual"] == Decimal("30000.00")
    # платёж 1 октября — до поступления 3 октября, лимит в день уменьшился
    assert "Спортзал" in [p["title"] for p in report["runway"]["paymentsBeforeIncome"]]
    assert (
        report["runway"]["todaySafeSpend"]
        < build_report(preset("student", "4092"), AS_OF)["runway"]["todaySafeSpend"]
    )


def test_empty_state_names_missing_data():
    report = build_report(UserState(), AS_OF)
    assert report["runway"] is None
    assert report["missing"] == [
        "операции хотя бы за один месяц",
        "текущий баланс",
        "регулярное поступление с датой: стипендия, зарплата или перевод",
    ]


def test_text_for_model_has_key_numbers(worker):
    text = report_text(build_report(worker, AS_OF))
    assert "Баланс сейчас: 21 000 ₽." in text
    assert "можно тратить 79 ₽ в день" in text
    assert "осталось 11,4% дохода" in text
    assert "{" not in text  # без JSON: короткие строки по-русски
