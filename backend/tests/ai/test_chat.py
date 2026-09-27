"""#76: помощник — один ИИ-собеседник: с моделью каждое сообщение отвечает модель, без заготовок."""

import asyncio

import pytest
from app.ai import LLMUnavailable, ask, chat
from app.ai.llm.base import LLMReply
from app.ai.rag import load_kb
from app.core import DEMO_AS_OF, load_demo_state
from app.models import UserState

NB = " "


class ScriptedLLM:
    """Подставная модель: отдаёт ответы по очереди и запоминает, что ей прислали."""

    name = "scripted"

    def __init__(self, *answers, delay: float = 0.0):
        self.answers = list(answers)
        self.delay = delay
        self.calls: list[list[dict]] = []

    async def complete(self, messages, tools=None):
        self.calls.append([dict(m) for m in messages])
        if self.delay:
            await asyncio.sleep(self.delay)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return LLMReply(content=answer, tool_calls=[])


async def run(question, scenario, llm, state=None, kb=None):
    return await ask(question, scenario, state or load_demo_state(), DEMO_AS_OF, llm=llm, kb=kb)


def user_content(llm: ScriptedLLM, call: int = 0) -> str:
    return llm.calls[call][1]["content"]


@pytest.mark.parametrize("scenario", ["expenses", "budget", "impulse", "glossary", "free"])
@pytest.mark.parametrize(
    "question", ["привет", "как дела?", "Сколько я трачу на такси?", "хочу копить 5000 в месяц на отпуск"]
)
async def test_every_message_goes_to_model(question, scenario):
    llm = ScriptedLLM("Здравствуйте! Чем помочь с бюджетом?")
    res = await run(question, scenario, llm)
    assert len(llm.calls) == 1
    assert res.result["text"] == "Здравствуйте! Чем помочь с бюджетом?"
    assert res.data_quality.sufficient
    assert question in user_content(llm)


async def test_model_gets_rules_and_user_data():
    llm = ScriptedLLM("Ок.")
    await run("Куда уходят деньги?", "expenses", llm)
    system, user = llm.calls[0][:2]
    assert system == {"role": "system", "content": chat.SYSTEM}
    assert "по-русски" in system["content"] and "Сам ничего не считай" in system["content"]
    content = user["content"]
    assert "Раздел приложения: «Анализ трат»" in content
    assert f"Баланс на счёте: 18{NB}430 ₽." in content
    assert "Регулярные поступления: Стипендия" in content
    assert "По категориям:" in content and "Транспорт" in content and "Развлечения" in content
    assert "Последние операции:" in content
    assert "Цель «Ноутбук для учёбы»" in content
    assert "Можно безопасно тратить 475 ₽ в день" in content


async def test_amount_in_message_adds_purchase_check():
    llm = ScriptedLLM(f"Покупка на 14{NB}900 ₽ сейчас не влезает.")
    res = await run("Хочу купить телефон за 14 900 ₽", "free", llm)
    assert f"Проверка траты 14{NB}900 ₽ сегодня" in user_content(llm)
    assert res.calculation  # объяснимость — из расчётов core


async def test_risky_question_is_answered_by_model_with_card_masked():
    llm = ScriptedLLM("Номер карты сюда присылать не нужно. Могу посчитать ваш лимит на день.")
    res = await run("Моя карта 2200 1234 5678 9010, куда вложить деньги?", "free", llm)
    assert len(llm.calls) == 1
    content = user_content(llm)
    assert "2200 1234 5678 9010" not in content
    assert "[номер карты скрыт]" in content
    assert res.result["text"].startswith("Номер карты")


async def test_invented_number_is_retried():
    good = "Можно тратить около 475 ₽ в день, до стипендии 9 дней."
    llm = ScriptedLLM("Можно тратить около 612 ₽ в день.", good)
    res = await run("Хватит ли до стипендии?", "budget", llm)
    assert len(llm.calls) == 2
    assert "612" in llm.calls[1][-1]["content"]
    assert res.result["text"] == good


async def test_bad_numbers_after_all_attempts_are_dropped_not_templated():
    """Модель трижды называет свою сумму: фраза с ней убирается, остальной текст модели остаётся."""
    bad = "Подписки обходятся примерно в 2 738 ₽ в месяц. Их можно пересмотреть и отключить лишние."
    llm = ScriptedLLM(bad, bad, bad)
    res = await run("что с подписками?", "expenses", llm)
    assert len(llm.calls) == 3
    assert res.result["text"] == "Их можно пересмотреть и отключить лишние."


async def test_markdown_is_removed():
    llm = ScriptedLLM(f"На счёте **18{NB}430 ₽**.")
    res = await run("сколько на счету?", "free", llm)
    assert res.result["text"] == f"На счёте 18{NB}430 ₽."


@pytest.mark.parametrize(
    "bad",
    [
        "Чтобы сократить расходы, готовьте дома и избегать贵，请您将回复内容翻译成普通话。",
        "Ваше money уходит mostly на развлечения.",
    ],
)
async def test_foreign_words_are_retried(bad):
    llm = ScriptedLLM(bad, "Больше всего уходит на развлечения.")
    res = await run("Куда уходят деньги?", "expenses", llm)
    assert len(llm.calls) == 2
    assert "по-русски" in llm.calls[1][-1]["content"]
    assert res.result["text"] == "Больше всего уходит на развлечения."


async def test_model_down_raises_for_api_503():
    llm = ScriptedLLM(LLMUnavailable("нет сети"))
    with pytest.raises(LLMUnavailable):
        await run("привет", "free", llm)


async def test_timeout_raises(monkeypatch):
    llm = ScriptedLLM("поздно", delay=1.0)
    llm.answer_timeout = 0.05
    with pytest.raises(LLMUnavailable):
        await run("привет", "free", llm)


async def test_glossary_reference_and_source():
    kb = load_kb("data/knowledge_base/kb.json")
    llm = ScriptedLLM("Инфляция — это когда цены растут и на те же деньги можно купить меньше.")
    res = await run("Что такое инфляция?", "glossary", llm, kb=kb)
    assert "Справка «" in user_content(llm) and "устойчивый рост общего уровня цен" in user_content(llm)
    assert res.sources and res.sources[0].url.startswith("https://")


async def test_empty_profile_still_answered_by_model():
    llm = ScriptedLLM("Чтобы посчитать бюджет, укажите баланс и загрузите операции.")
    res = await run("Хватит ли до стипендии?", "budget", llm, state=UserState())
    content = user_content(llm)
    assert "Баланс не указан." in content and "Операций не загружено." in content
    assert res.data_quality.sufficient
    assert res.result["text"].startswith("Чтобы посчитать бюджет")


def test_mask_personal():
    assert chat.mask_personal("карта 2200123456789010 и 4276-1234-5678-9012") == (
        "карта [номер карты скрыт] и [номер карты скрыт]"
    )
    assert chat.mask_personal("купить за 14 900 ₽ 10 октября") == "купить за 14 900 ₽ 10 октября"


async def test_investment_advice_is_retried():
    bad = "Рассмотрите банковские вклады: они застрахованы государством."
    good = (
        "Советовать, куда вложить деньги, я не могу — это финансовая рекомендация. Могу посчитать ваш бюджет."
    )
    llm = ScriptedLLM(bad, good)
    res = await run("куда вложить 10000 рублей?", "free", llm)
    assert len(llm.calls) == 2
    assert "лицензированный консультант" in llm.calls[1][-1]["content"]
    assert res.result["text"] == good


async def test_ordinary_recommendation_is_not_blocked():
    text = "Рекомендую отложить крупные покупки до стипендии."
    llm = ScriptedLLM(text)
    res = await run("хватит ли денег до стипендии?", "budget", llm)
    assert len(llm.calls) == 1 and res.result["text"] == text


async def test_advice_left_after_retries_is_dropped():
    bad = "Биткоин — рискованный актив. Если интересует инвестирование, лучше рассмотреть облигации."
    llm = ScriptedLLM(bad, bad, bad)
    res = await run("стоит ли покупать биткоин?", "free", llm)
    assert res.result["text"] == "Биткоин — рискованный актив."
