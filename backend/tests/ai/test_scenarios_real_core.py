"""Сценарии на настоящих расчётах Саши (SF3) и демо-профиле: числа сценария handoff.md."""

import pytest
from app.ai import ask
from app.core import DEMO_AS_OF, load_demo_state

NB = " "


async def run(question: str, scenario: str):
    return await ask(question, scenario, load_demo_state(), DEMO_AS_OF)


@pytest.mark.parametrize(
    ("question", "fragments"),
    [
        ("Хочу купить телефон за 14 900 ₽", ["не влезает", "«Подработка» 10 октября"]),
        ("Можно потратить 3000?", ["лучше отложить", "с 475 ₽", "«Стипендия» 5 октября"]),
        ("Куплю наушники за 500 ₽", ["влезает", "420 ₽ вместо 475 ₽"]),
    ],
)
async def test_impulse_demo(question, fragments):
    res = await run(question, "impulse")
    assert res.data_quality.sufficient
    for fragment in fragments:
        assert fragment in res.result["text"]
    assert res.calculation


async def test_budget_demo():
    res = await run("Хватит ли мне денег до конца месяца?", "free")
    text = res.result["text"]
    assert "около 475 ₽ в день" in text
    assert "«Стипендия» 9 дней" in text
    labels = [(s.label, s.value) for s in res.calculation]
    assert len(labels) == len(set(labels))


async def test_expenses_demo():
    res = await run("Куда уходят деньги?", "expenses")
    assert res.data_quality.sufficient
    assert f"Жильё — 12{NB}000 ₽" in res.result["text"]
