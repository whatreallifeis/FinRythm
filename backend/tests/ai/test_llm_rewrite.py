"""AF5: модель переписывает шаблонный ответ; проверка чисел, повтор, шаблон, таймаут, провайдер."""

import asyncio
import importlib
import json
import time
from types import SimpleNamespace

import httpx
import pytest
from app.ai import LLMUnavailable, ask, get_llm, prompts
from app.ai.answer_check import split_verdict
from app.ai.llm.base import LLMReply
from app.ai.llm.factory import llm_timeout
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

    cancelled = False

    async def complete(self, messages, tools=None):
        self.calls.append([dict(m) for m in messages])
        if self.delay:
            try:
                await asyncio.sleep(self.delay)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return LLMReply(content=answer)


async def verdict_of(question, scenario, kb=None):
    """Первая фраза шаблонного ответа — её модель не переписывает."""
    template = await run(question, scenario, None, kb=kb)
    return split_verdict(template.result["text"])[0]


async def run(question, scenario, llm, state=None, kb=None):
    return await ask(question, scenario, state or load_demo_state(), DEMO_AS_OF, llm=llm, kb=kb)


async def test_model_text_used_when_numbers_ok():
    llm = ScriptedLLM(GOOD_14900)
    res = await run("Хочу купить телефон за 14 900 ₽", "impulse", llm)
    verdict = await verdict_of("Хочу купить телефон за 14 900 ₽", "impulse")
    assert res.result["text"] == f"{verdict} {GOOD_14900}"
    system, user = llm.calls[0]
    assert system == {"role": "system", "content": prompts.SYSTEM}
    assert "на «вы»" in system["content"]
    assert user["content"].startswith("Задача: Объясни, влезет ли покупка")
    assert "Первая фраза (уже написана): Сейчас покупка на 14" in user["content"]
    assert "Остальное из черновика: Безопаснее подождать" in user["content"]
    # расчёт в промпт не идёт — модель видит только черновик (issue #39: короче промпт на CPU)
    assert "verdict" not in user["content"] and "{" not in user["content"]
    assert len(system["content"]) + len(user["content"]) < 1200
    # объяснимость — из core, модель её не меняет
    assert [s.label for s in res.calculation][0] == "Покупка"


async def test_system_prompt_is_the_same_for_all_scenarios():
    prompts_seen = []
    for question, scenario in [("Составь бюджет", "budget"), ("Куда уходят деньги?", "expenses")]:
        llm = ScriptedLLM("Ответ без чисел.")
        await run(question, scenario, llm)
        prompts_seen.append(llm.calls[0][0]["content"])
    assert prompts_seen[0] == prompts_seen[1]


async def test_retry_after_invented_number():
    llm = ScriptedLLM("Покупка на 14 900 ₽ не влезает, до минуса 13 333 ₽.", GOOD_14900)
    res = await run("Хочу купить телефон за 14 900 ₽", "impulse", llm)
    assert res.result["text"].endswith(GOOD_14900)
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
    assert res.result["text"].endswith(GOOD_14900)
    assert "по-русски" in llm.calls[1][-1]["content"]


async def test_provider_error_gives_template():
    res = await run("Составь бюджет", "budget", ScriptedLLM(LLMUnavailable("down")))
    assert res.result["text"].startswith("До конца месяца можно тратить около 475")


async def test_timeout_gives_template_and_cancels_request():
    llm = ScriptedLLM("текст", delay=5)
    llm.answer_timeout = 0.2
    started = time.monotonic()
    res = await run("Составь бюджет", "budget", llm)
    assert time.monotonic() - started < 2
    assert res.result["text"].startswith("До конца месяца можно тратить около 475")
    assert llm.cancelled  # запрос к модели отменён, Ollama не держит брошенный ответ


async def test_no_retry_without_time_left():
    llm = ScriptedLLM("Лимит 999 ₽.", GOOD_14900)
    llm.answer_timeout = ask_module.MIN_RETRY_SECONDS / 2
    res = await run("Хочу купить телефон за 14 900 ₽", "impulse", llm)
    assert len(llm.calls) == 1
    assert res.result["text"].startswith("Сейчас покупка на 14")


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


async def test_free_uses_task_of_detected_scenario_and_one_call():
    llm = ScriptedLLM("Больше всего денег уходит на развлечения — там и проще сократить.")
    await run("Как мне меньше тратить на еду?", "free", llm)
    assert len(llm.calls) == 1  # сценарий выбран по словам, модель вызвана один раз
    assert llm.calls[0][1]["content"].startswith("Задача: Объясни, куда уходят деньги")


async def test_glossary_gets_source_text():
    from app.ai.rag import load_kb

    kb = load_kb("data/knowledge_base/kb.json")
    answer = (
        "Инфляция — это когда цены растут и на те же деньги можно купить меньше. Типичная ошибка: путать."
    )
    llm = ScriptedLLM(answer)
    res = await run("Что такое инфляция?", "glossary", llm, kb=kb)
    verdict = await verdict_of("Что такое инфляция?", "glossary", kb=kb)
    assert res.result["text"] == f"{verdict} {answer}"
    assert "устойчивый рост общего уровня цен" in llm.calls[0][1]["content"]
    assert res.sources[0].url.startswith("https://fincult.info/")


@pytest.mark.parametrize("with_model", [False, True])
async def test_decide_for_me_shows_both_options(with_model):
    # issue #29: последствия и покупки, и отказа от неё; модель текст не трогает (#39: убирала «решать вам»)
    llm = ScriptedLLM() if with_model else None
    res = await run("Реши за меня, покупать наушники за 14 900 или нет", "impulse", llm)
    text = res.result["text"]
    if llm is not None:
        assert llm.calls == []
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


@pytest.mark.parametrize(
    ("raw", "tidy"),
    [
        ("баланс уйдёт в минус до -10618 ₽", "баланс уйдёт в минус до −10\u00a0618 ₽"),
        ("лимит 4900 ₽ в день", "лимит 4\u00a0900 ₽ в день"),
        ("к 1 февраля 2027 года", "к 1 февраля 2027 года"),
        ("операция t-901", "операция t-901"),
        ("14\u00a0900 ₽ и 3–6 месяцев", "14\u00a0900 ₽ и 3–6 месяцев"),
    ],
)
def test_tidy_numbers(raw, tidy):
    assert ask_module.tidy_numbers(raw) == tidy


def test_llm_timeout_setting(monkeypatch):
    monkeypatch.delenv("LLM_TIMEOUT", raising=False)
    assert llm_timeout(SimpleNamespace()) == 40
    assert llm_timeout(SimpleNamespace(llm_timeout=25)) == 25
    monkeypatch.setenv("LLM_TIMEOUT", "90")
    assert llm_timeout(SimpleNamespace()) == 90
    monkeypatch.setenv("LLM_TIMEOUT", "много")
    assert llm_timeout(SimpleNamespace()) == 40
    settings = SimpleNamespace(
        llm_provider="openai_compat", llm_base_url="http://x/v1", llm_model="m", llm_api_key=""
    )
    assert get_llm(settings).answer_timeout == 40
