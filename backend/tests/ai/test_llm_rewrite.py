"""AF5: модель переписывает шаблонный ответ; проверка чисел, повтор, шаблон, таймаут, провайдер."""

import asyncio
import importlib
import json
from types import SimpleNamespace

import httpx
import pytest
from app.ai import LLMUnavailable, ask, get_llm
from app.ai.llm.base import LLMReply
from app.ai.llm.openai_compat import OpenAICompatLLM
from app.core import DEMO_AS_OF, load_demo_state

ask_module = importlib.import_module("app.ai.ask")

NB = "\u00a0"
GOOD_14900 = (
    f"К сожалению, покупка на 14{NB}900 ₽ сейчас не влезает: баланс уйдёт в минус до −10{NB}618 ₽. "
    "Лучше подождать «Подработку» 10 октября."
)


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
        return LLMReply(content=answer)


async def run(question, scenario, llm, state=None, kb=None):
    return await ask(question, scenario, state or load_demo_state(), DEMO_AS_OF, llm=llm, kb=kb)


async def test_model_text_used_when_numbers_ok():
    llm = ScriptedLLM(GOOD_14900)
    res = await run("Хочу купить телефон за 14 900 ₽", "impulse", llm)
    assert res.result["text"] == GOOD_14900
    system, user = llm.calls[0]
    assert system["role"] == "system" and "Могу купить это сегодня" in system["content"]
    assert "2026-09-26" in system["content"] and "на «вы»" in system["content"]
    assert "Черновик ответа: Сейчас покупка на 14" in user["content"]
    assert '"verdict": "shortfall"' in user["content"]
    assert "daysAfter" not in user["content"]  # длинные списки по дням модели не отправляем
    # объяснимость — из core, модель её не меняет
    assert [s.label for s in res.calculation][0] == "Покупка"


async def test_retry_after_invented_number():
    llm = ScriptedLLM("Покупка на 14 900 ₽ не влезает, до минуса 13 333 ₽.", GOOD_14900)
    res = await run("Хочу купить телефон за 14 900 ₽", "impulse", llm)
    assert res.result["text"] == GOOD_14900
    assert len(llm.calls) == 2
    assert "13333" in llm.calls[1][-1]["content"]  # подсказка называет выдуманное число


async def test_template_after_two_bad_answers():
    llm = ScriptedLLM("Лимит 999 ₽.", "Лимит 998 ₽.")
    res = await run("Хочу купить телефон за 14 900 ₽", "impulse", llm)
    assert res.result["text"].startswith("Сейчас покупка на 14")
    assert "999" not in res.result["text"]


async def test_english_answer_is_retried():
    llm = ScriptedLLM("You cannot afford it.", GOOD_14900)
    res = await run("Хочу купить телефон за 14 900 ₽", "impulse", llm)
    assert res.result["text"] == GOOD_14900
    assert "по-русски" in llm.calls[1][-1]["content"]


async def test_provider_error_is_llm_unavailable():
    with pytest.raises(LLMUnavailable):
        await run("Составь бюджет", "budget", ScriptedLLM(LLMUnavailable("down")))


async def test_timeout_is_llm_unavailable(monkeypatch):
    monkeypatch.setattr(ask_module, "ANSWER_TIMEOUT", 0.05)
    with pytest.raises(LLMUnavailable):
        await run("Составь бюджет", "budget", ScriptedLLM("текст", delay=1))


@pytest.mark.parametrize(
    ("question", "scenario"),
    [
        ("Взять микрозайм до стипендии?", "free"),  # отказ
        ("Можно сегодня что-нибудь купить?", "impulse"),  # нет суммы
        ("Привет, как дела?", "free"),  # просим уточнить
    ],
)
async def test_model_not_called_without_answer(question, scenario):
    llm = ScriptedLLM()
    await run(question, scenario, llm)
    assert llm.calls == []


async def test_fake_provider_keeps_template():
    res = await run(
        "Хочу купить телефон за 14 900 ₽", "impulse", get_llm(SimpleNamespace(llm_provider="fake"))
    )
    assert res.result["text"].startswith("Сейчас покупка на 14")


async def test_free_uses_prompt_of_detected_scenario():
    llm = ScriptedLLM("До конца месяца можно тратить около 475 ₽ в день.")
    await run("Хватит ли мне денег до конца месяца?", "free", llm)
    assert "Планирование бюджета" in llm.calls[0][0]["content"]


async def test_glossary_gets_source_text():
    from app.ai.rag import load_kb

    kb = load_kb("data/knowledge_base/kb.json")
    answer = (
        "Инфляция — это когда цены растут и на те же деньги можно купить меньше. Типичная ошибка: путать."
    )
    llm = ScriptedLLM(answer)
    res = await run("Что такое инфляция?", "glossary", llm, kb=kb)
    assert res.result["text"] == answer
    assert "устойчивый рост общего уровня цен" in llm.calls[0][1]["content"]
    assert res.sources[0].url.startswith("https://fincult.info/")


async def test_decide_for_me_shows_both_options():
    # issue #29: последствия и покупки, и отказа от неё
    res = await run("Реши за меня, покупать наушники за 14 900 или нет", "impulse", None)
    text = res.result["text"]
    assert text.startswith("Решать вам")
    assert "не влезает" in text
    assert "Если не покупать — можно тратить 475 ₽ в день, дней в минусе не будет." in text


# ---------------------------------------------------------------- провайдер openai_compat


def http_llm(handler) -> OpenAICompatLLM:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICompatLLM(
        base_url="http://ollama.test/v1", model="qwen2.5:7b", api_key="ollama", http_client=client
    )


def completion(content: str) -> dict:
    return {
        "id": "c1",
        "object": "chat.completion",
        "created": 0,
        "model": "qwen2.5:7b",
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}
        ],
    }


async def test_openai_compat_request_and_reply():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=completion("Привет"))

    reply = await http_llm(handler).complete([{"role": "user", "content": "вопрос"}])
    assert reply.content == "Привет"
    assert seen["url"] == "http://ollama.test/v1/chat/completions"
    assert seen["body"]["model"] == "qwen2.5:7b"


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(500, json={"error": {"message": "boom"}}),
        lambda request: (_ for _ in ()).throw(httpx.ConnectError("refused")),
        lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow")),
    ],
)
async def test_openai_compat_failures_are_llm_unavailable(handler):
    with pytest.raises(LLMUnavailable):
        await http_llm(handler).complete([{"role": "user", "content": "вопрос"}])


def test_factory_openai_compat():
    llm = get_llm(
        SimpleNamespace(
            llm_provider="openai_compat",
            llm_base_url="http://localhost:11434/v1",
            llm_model="qwen2.5:7b",
            llm_api_key="ollama",
        )
    )
    assert isinstance(llm, OpenAICompatLLM)
    assert llm.model == "qwen2.5:7b"


def test_factory_openai_compat_needs_url_and_model():
    with pytest.raises(ValueError, match="LLM_BASE_URL, LLM_MODEL"):
        get_llm(SimpleNamespace(llm_provider="openai_compat", llm_base_url="", llm_model=""))


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("«Покупка влезает.»", "Покупка влезает."),
        ("Подождите «Подработку»", "Подождите «Подработку»"),
        ('  "Текст"  ', "Текст"),
        ("строка\n\nвторая", "строка вторая"),
    ],
)
def test_clean(raw, clean):
    assert ask_module._clean(raw) == clean
