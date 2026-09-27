"""Провайдер openai_compat и утилиты текста модели. Поведение чата с моделью — test_chat.py (#76)."""

import importlib
import json
from types import SimpleNamespace

import httpx
import pytest
from app.ai import LLMUnavailable, get_llm
from app.ai.llm.factory import llm_timeout
from app.ai.llm.openai_compat import OpenAICompatLLM

ask_module = importlib.import_module("app.ai.ask")

NB = "\u00a0"
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
