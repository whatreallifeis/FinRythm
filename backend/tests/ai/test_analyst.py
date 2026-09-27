"""Помощник-аналитик: модель отвечает по сводке, числа сверяются, при ошибке — шаблон."""

import pytest
from app.ai import ask
from app.ai.analyst import clean, informal_problem, junk_problem, label_problem
from app.ai.llm.base import LLMReply, LLMUnavailable
from app.core import DEMO_AS_OF, load_demo_state
from app.models import UserState

NB = " "


class ScriptedLLM:
    name = "scripted"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list[list[dict]] = []

    async def complete(self, messages, tools=None):
        self.calls.append([dict(m) for m in messages])
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return LLMReply(content=answer)


async def run(question, scenario, llm, state=None):
    return await ask(question, scenario, state or load_demo_state(), DEMO_AS_OF, llm=llm)


async def test_answer_with_numbers_from_report_is_accepted():
    answer = f"Сейчас на счёте 18{NB}430 ₽. Главное — не тратить больше лимита в день."
    llm = ScriptedLLM(answer)
    res = await run("Есть ли у меня финансовый риск?", "free", llm)
    assert res.result["text"] == answer
    assert res.data_quality.sufficient
    assert res.calculation[0].label == "Баланс"
    assert "GigaChat" in res.assumptions[0]
    assert len(llm.calls) == 1


async def test_invented_number_is_retried_with_hint():
    good = f"На счёте 18{NB}430 ₽ — этого хватает."
    llm = ScriptedLLM("Вы потратили 123 457 ₽ за месяц.", good)
    res = await run("Хватит ли денег?", "free", llm)
    assert res.result["text"] == good
    assert "123457" in llm.calls[1][-1]["content"]  # подсказка называет выдуманное число


async def test_two_bad_answers_fall_back_to_template_without_more_calls():
    llm = ScriptedLLM("Ровно 999 999 ₽.", "Снова 888 888 ₽.")
    res = await run("Куда уходят деньги?", "expenses", llm)
    template = await run("Куда уходят деньги?", "expenses", None)
    assert res.result["text"] == template.result["text"]
    assert len(llm.calls) == 2  # после отказа аналитика модель больше не зовём


async def test_provider_error_falls_back_to_template():
    llm = ScriptedLLM(LLMUnavailable("нет сети"))
    res = await run("Куда уходят деньги?", "expenses", llm)
    assert res.result["text"]
    assert len(llm.calls) == 1


async def test_risky_question_is_refused_before_the_model():
    llm = ScriptedLLM()
    res = await run("Где взять микрозайм до стипендии?", "free", llm)
    assert llm.calls == []
    assert res.result["text"]


async def test_no_transactions_gives_insufficient_data_without_model():
    llm = ScriptedLLM()
    res = await run("Куда уходят деньги?", "expenses", llm, state=UserState())
    assert llm.calls == []
    assert not res.data_quality.sufficient


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("**Итог:** всё хорошо.", "Итог: всё хорошо."),
        ("Первое.\n- пункт один\n- пункт два", "Первое. пункт один пункт два"),
        ("«Ответ целиком в кавычках»", "Ответ целиком в кавычках"),
    ],
)
def test_clean_removes_markup(raw, expected):
    assert clean(raw) == expected


def test_list_of_bare_numbers_is_rejected():
    assert junk_problem("Траты выросли. 62, 12 280 ₽, 6, 8 000 ₽, 9, 4 249 ₽.")
    assert junk_problem("В сентябре 12 280 ₽ ушло на прочее, 6 268 ₽ на еду и 4 249 ₽ на кафе.") is None
    assert junk_problem("Доходы 46 000 ₽, расходы 40 758 ₽, итог 5 242 ₽.") is None


async def test_answer_with_bare_numbers_is_retried():
    good = f"На счёте 18{NB}430 ₽ — этого хватает."
    llm = ScriptedLLM("Остаток 18 430, 1, 100.", good)
    res = await run("Хватит ли денег?", "free", llm)
    assert res.result["text"] == good
    assert "список чисел" in llm.calls[1][-1]["content"]


@pytest.mark.parametrize(
    ("text", "bad"),
    [
        ("Успеешь накопить к сроку.", True),
        ("Тебе нужно откладывать больше.", True),
        ("Вы успеваете к сроку, откладывайте 3 992 ₽ в месяц.", False),
        ("Меньше тратьте на еду вне дома.", False),
    ],
)
def test_informal_address_is_detected(text, bad):
    assert (informal_problem(text) is not None) is bad


@pytest.mark.parametrize(
    ("text", "bad"),
    [
        ("До аванса 14 дней. Числа: «14 дн.», «79 ₽ в день».", True),
        ("По вашим данным: данные: расходы 12 280 ₽.", True),
        ("Сократите кафе. Дальше можно: пересмотреть подписки.", False),
        ("До аванса 14 дней, можно тратить 79 ₽ в день.", False),
        ("Цель «Отпуск»: откладывайте 3 992 ₽ в месяц.", False),
    ],
)
def test_service_labels_are_detected(text, bad):
    assert (label_problem(text) is not None) is bad


async def test_free_question_gets_digest_when_model_fails():
    llm = ScriptedLLM("Ровно 999 999 ₽.", "Снова 888 888 ₽.")
    res = await run("Есть ли у меня финансовый риск?", "free", llm)
    assert res.data_quality.sufficient  # не «уточните вопрос», а короткая сводка
    assert "можно тратить" in res.result["text"]
    assert "не ответила" in res.assumptions[0]
