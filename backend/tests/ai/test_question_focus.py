"""Шаблоны без модели (LLM_PROVIDER=fake): приветствие, категория, баланс. С моделью — test_chat.py."""

import pytest
from app.ai import ask, scenarios
from app.core import DEMO_AS_OF, load_demo_state

NB = " "


async def run(question: str, scenario: str, llm=None):
    return await ask(question, scenario, load_demo_state(), DEMO_AS_OF, llm=llm)


@pytest.mark.parametrize("scenario", ["expenses", "budget", "impulse", "glossary", "free"])
@pytest.mark.parametrize("question", ["привет", "Здравствуйте!", "спасибо", "Как дела?", "что ты умеешь?"])
async def test_smalltalk_in_every_scenario(question, scenario):
    res = await run(question, scenario)
    assert res.data_quality.sufficient
    text = res.result["text"]
    assert text.startswith("Здравствуйте!")
    assert "₽" not in text.split("Спросите")[0]  # не отчёт с числами
    assert scenarios.EXAMPLES[scenario] in text


@pytest.mark.parametrize(
    "question",
    [
        "Привет, можно купить наушники за 4900?",
        "привет, сколько я трачу на еду?",
        "Здравствуйте, что такое инфляция?",
    ],
)
def test_greeting_with_real_question_is_not_smalltalk(question):
    assert not scenarios.looks_like_smalltalk(question)


@pytest.mark.parametrize(
    ("question", "category", "fragment"),
    [
        ("Сколько я трачу на такси?", "transport", "На категорию «Транспорт»"),
        ("а что с подписками?", "subscriptions", "На категорию «Подписки и связь»"),
        ("Сколько уходит на еду?", "food", "На категорию «Еда»"),
        ("Сколько я трачу на аренду?", "rent", "На категорию «Жильё»"),
    ],
)
async def test_expenses_answers_about_asked_category(question, category, fragment):
    assert scenarios.asked_category(question) == category
    res = await run(question, "expenses")
    text = res.result["text"]
    assert text.startswith(fragment), text
    assert "всех расходов" in text.split(".")[0] or "трат нет" in text.split(".")[0]


async def test_expenses_general_question_keeps_overview():
    res = await run("Куда уходят мои деньги?", "expenses")
    assert res.result["text"].startswith("С 1 сентября по 26 сентября расходы")


async def test_free_category_question_goes_to_expenses():
    res = await run("а что с подписками?", "free")
    assert res.data_quality.sufficient
    assert res.result["text"].startswith("На категорию «Подписки и связь»")


@pytest.mark.parametrize(
    "question", ["Сколько у меня на счету?", "какой у меня баланс", "сколько у меня денег сейчас?"]
)
async def test_balance_question(question):
    res = await run(question, "free")
    assert res.data_quality.sufficient
    text = res.result["text"]
    assert text.startswith(f"На счёте сейчас 18{NB}430 ₽.")
    assert "«Стипендия»" in text and "475 ₽ в день" in text


async def test_balance_unknown():
    from app.models import UserState

    res = await ask("Сколько у меня на счету?", "free", UserState(), DEMO_AS_OF)
    assert not res.data_quality.sufficient
    assert res.data_quality.missing == [scenarios.MISSING_BALANCE]
