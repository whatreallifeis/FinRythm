"""Модели фронтенда (раздел «модели фронтенда» в app.models): валидация и сериализация."""

from datetime import date
from decimal import Decimal

import pytest
from app.models import (
    CATEGORY_IDS,
    SCENARIO_IDS,
    CalcStep,
    DataQuality,
    Explained,
    ImportResult,
    ImportRow,
    IncomeRule,
    Operation,
    RejectedRow,
    SavingGoal,
    UserState,
)
from pydantic import ValidationError


def test_category_and_scenario_lists_match_frontend():
    assert CATEGORY_IDS == (
        "food",
        "transport",
        "subscriptions",
        "entertainment",
        "health",
        "education",
        "rent",
        "other",
    )
    assert SCENARIO_IDS == ("expenses", "budget", "glossary", "impulse", "free")


def test_operation_defaults_and_money_is_decimal():
    op = Operation(id="t-1", date=date(2026, 9, 20), amount="-349.00")
    assert op.amount == Decimal("-349.00")
    assert isinstance(op.amount, Decimal)
    assert op.category == "other"
    assert op.merchant == ""
    assert op.is_recurring is False


def test_operation_rejects_unknown_category():
    with pytest.raises(ValidationError):
        Operation(id="t-1", date=date(2026, 9, 20), amount="-1", category="Продукты")


@pytest.mark.parametrize("day", [0, 32])
def test_income_rule_day_of_month_bounds(day):
    with pytest.raises(ValidationError):
        IncomeRule(id="i-1", title="Стипендия", amount="8000", day_of_month=day)


def test_income_rule_amount_must_be_positive():
    with pytest.raises(ValidationError):
        IncomeRule(id="i-1", title="Стипендия", amount="0", day_of_month=5)


def test_goal_saved_cannot_exceed_target():
    with pytest.raises(ValidationError, match="Накоплено не может быть больше суммы цели"):
        SavingGoal(id="g-1", title="Ноутбук", target_amount="60000", saved_amount="60000.01")


def test_goal_without_deadline_is_allowed():
    goal = SavingGoal(id="g-1", title="Ноутбук", target_amount="60000")
    assert goal.deadline is None
    assert goal.saved_amount == Decimal("0")


def test_user_state_empty_and_roundtrip_through_json():
    assert UserState().model_dump() == {
        "balance": None,
        "incomes": [],
        "autopayments": [],
        "goals": [],
        "transactions": [],
        "history": [],
    }
    state = UserState(
        balance="18430.00",
        incomes=[IncomeRule(id="i-1", title="Стипендия", amount="8000", day_of_month=5)],
        goals=[SavingGoal(id="g-1", title="Ноутбук", target_amount="60000", deadline=date(2027, 6, 1))],
        transactions=[Operation(id="t-1", date=date(2026, 9, 20), amount="-349", category="food")],
        history=[{"id": "h-1", "scenarioId": "free", "title": "Вопрос", "createdAt": "x", "messages": []}],
    )
    restored = UserState.model_validate_json(state.model_dump_json())
    assert restored == state
    assert restored.balance == Decimal("18430.00")


def test_user_state_rejects_negative_balance():
    with pytest.raises(ValidationError):
        UserState(balance="-1")


def test_import_row_keeps_unknown_category_for_ingest_to_decide():
    row = ImportRow(date=date(2026, 9, 1), amount="-100", category="Кафе")
    assert row.category == "Кафе"


def test_import_result_rows_start_from_one():
    with pytest.raises(ValidationError):
        RejectedRow(row=0, message="Пустая сумма")
    result = ImportResult(imported=2, rejected=[RejectedRow(row=3, message="Пустая сумма")])
    assert result.warnings == []


def test_explained_shape():
    payload = Explained(
        result={"todaySafeSpend": Decimal("650")},
        calculation=[CalcStep(label="Можно тратить в день", formula="7 800 ₽ / 12 дн.", value="650")],
        data_quality=DataQuality(sufficient=True, coverage_days=60),
    )
    dumped = payload.model_dump()
    assert set(dumped) == {"result", "assumptions", "calculation", "sources", "limitations", "data_quality"}
    assert dumped["calculation"][0]["value"] == Decimal("650")
    assert dumped["data_quality"] == {"sufficient": True, "missing": [], "coverage_days": 60}
