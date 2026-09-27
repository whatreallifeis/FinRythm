"""Issue #65: смесь языков и искажённый смысл в ответе модели → повтор, затем шаблон."""

import pytest
from app.ai import ask
from app.ai.answer_check import language_problem, meaning_problem, split_verdict
from app.ai.llm.base import LLMReply
from app.core import DEMO_AS_OF, load_demo_state

NB = "\u00a0"


class ScriptedLLM:
    name = "scripted"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    async def complete(self, messages, tools=None):
        self.calls.append(messages)
        return LLMReply(content=self.answers.pop(0))


async def run(question, scenario, llm):
    return await ask(question, scenario, load_demo_state(), DEMO_AS_OF, llm=llm)


# Реальные ответы qwen2.5 из #65: каждый проходил старую проверку («есть кириллица», числа верные).
BAD_ANSWERS = [
    (
        "Как мне меньше тратить на еду?",
        "free",
        "Чтобы сократить расходы, можно попробовать готовить дома чаще "
        "и избегать贵，请您将回复内容翻译成普通话。",
    ),
    ("Куда уходят мои деньги?", "expenses", "Ваше money уходит mostly на развлечения и жильё."),
    (
        "Хватит ли мне денег до стипендии, если я коплю на ноутбук?",
        "budget",
        f"На ноутбук вы сможете накопить около 12{NB}657 ₽.",
    ),
    ("Могу купить наушники за 14 900 сегодня?", "impulse", "Да, сегодня наушники не влезут."),
]


@pytest.mark.parametrize(("question", "scenario", "bad"), BAD_ANSWERS)
async def test_bad_model_answers_fall_back_to_template(question, scenario, bad):
    llm = ScriptedLLM(bad, bad)
    res = await run(question, scenario, llm)
    template = (await run(question, scenario, None)).result["text"]
    assert res.result["text"] == template
    assert len(llm.calls) == 2  # была повторная попытка с подсказкой
    hint = llm.calls[1][-1]["content"]
    assert "Исправь продолжение" in hint or "по-русски" in hint


async def test_retry_fixes_the_answer():
    good = f"Чтобы успеть к сроку, откладывайте около 12{NB}657 ₽ в месяц."
    llm = ScriptedLLM(f"На ноутбук вы сможете накопить около 12{NB}657 ₽.", good)
    res = await run("Хватит ли мне денег до стипендии, если я коплю на ноутбук?", "budget", llm)
    assert res.result["text"].startswith("До конца месяца можно тратить около 475 ₽ в день")
    assert res.result["text"].endswith(good)
    assert "в месяц" in llm.calls[1][-1]["content"]


async def test_verdict_is_kept_verbatim():
    llm = ScriptedLLM("Лучше дождаться подработки 10 октября — тогда покупка не выведет вас в минус.")
    res = await run("Могу купить наушники за 14 900 сегодня?", "impulse", llm)
    assert res.result["text"].startswith(f"Сейчас покупка на 14{NB}900 ₽ не влезает")


def test_split_verdict():
    assert split_verdict("Покупка влезает. Лимит станет 420 ₽.") == (
        "Покупка влезает.",
        "Лимит станет 420 ₽.",
    )
    assert split_verdict("Одна фраза без продолжения.") == ("Одна фраза без продолжения.", "")
    # точка в числе — не конец фразы
    assert split_verdict("Доля 0.39 от расходов. Дальше.")[0] == "Доля 0.39 от расходов."


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("Можно готовить дома и избегать贵", "иероглифы"),
        ("Ваше money уходит mostly на развлечения", "money, mostly"),
        ("Нормальный русский ответ про кешбэк.", None),
        ("Никому не сообщайте CVC-код и PIN.", None),  # разрешённые сокращения
        ("Оплата частями через BNPL-сервис.", None),
    ],
)
def test_language_problem(text, problem):
    found = language_problem(text)
    if problem is None:
        assert found is None
    else:
        assert problem in found


def test_latin_from_question_or_source_is_allowed():
    assert (
        language_problem("Кешбэк (cashback) — возврат части денег.", ["Кешбэк (от английского cashback)"])
        is None
    )


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        (f"Откладывайте около 12{NB}657 ₽ в месяц.", True),
        (f"Вы сможете накопить около 12{NB}657 ₽.", False),
        ("Можно тратить 475 ₽ в день.", True),
        ("У вас есть 475 ₽.", False),
        ("Да, покупка не влезет.", False),
        ("Данные показывают, что лучше подождать.", True),  # «Данные» — не «да»
    ],
)
def test_meaning_problem(text, ok):
    draft = (
        f"До конца месяца можно тратить около 475 ₽ в день. На цель откладывайте около 12{NB}657 ₽ в месяц."
    )
    assert (meaning_problem(text, draft) is None) is ok
