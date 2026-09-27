"""Провайдер GigaChat: авторизация по ключу, токен на 30 минут, ошибки → LLMUnavailable."""

import json
import time
from types import SimpleNamespace

import httpx
import pytest
from app.ai import LLMUnavailable, ask, get_llm
from app.ai.llm.gigachat import AUTH_URL, CA_FILE, GigaChatLLM, ssl_context
from app.core import DEMO_AS_OF, load_demo_state

NB = "\u00a0"
GOOD = f"Покупка на 14{NB}900 ₽ сейчас не влезает: лучше подождать «Подработку» 10 октября."


class FakeGigaChat:
    """Подставные сервер авторизации и API чата."""

    def __init__(self, answers=(GOOD,), chat_status=200, auth_status=200, expires_in=1800):
        self.answers = list(answers)
        self.chat_status = list(chat_status) if isinstance(chat_status, list) else [chat_status]
        self.auth_status = auth_status
        self.expires_in = expires_in
        self.auth_calls: list[httpx.Request] = []
        self.chat_calls: list[dict] = []
        self.tokens = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == AUTH_URL:
            self.auth_calls.append(request)
            if self.auth_status != 200:
                return httpx.Response(self.auth_status, json={"message": "no"})
            self.tokens += 1
            expires_at = int((time.time() + self.expires_in) * 1000)
            return httpx.Response(
                200, json={"access_token": f"token-{self.tokens}", "expires_at": expires_at}
            )
        assert str(request.url) == "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        self.chat_calls.append(
            {"auth": request.headers["Authorization"], "body": json.loads(request.content)}
        )
        status = self.chat_status.pop(0) if len(self.chat_status) > 1 else self.chat_status[0]
        if status != 200:
            return httpx.Response(status, json={"message": "error"})
        content = self.answers.pop(0) if self.answers else GOOD
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


def llm_for(server: FakeGigaChat, **kwargs) -> GigaChatLLM:
    client = httpx.AsyncClient(transport=httpx.MockTransport(server))
    return GigaChatLLM(credentials="c2VjcmV0", http_client=client, **kwargs)


async def test_auth_then_chat():
    server = FakeGigaChat()
    reply = await llm_for(server).complete([{"role": "user", "content": "вопрос"}])
    assert reply.content == GOOD
    auth = server.auth_calls[0]
    assert auth.headers["Authorization"] == "Basic c2VjcmV0"
    assert auth.headers["RqUID"]
    assert auth.content == b"scope=GIGACHAT_API_PERS"
    call = server.chat_calls[0]
    assert call["auth"] == "Bearer token-1"
    assert call["body"]["model"] == "GigaChat"
    assert call["body"]["max_tokens"] == 300
    assert call["body"]["messages"] == [{"role": "user", "content": "вопрос"}]


async def test_token_is_reused_until_expiry():
    server = FakeGigaChat(answers=[GOOD, GOOD])
    llm = llm_for(server)
    await llm.complete([{"role": "user", "content": "1"}])
    await llm.complete([{"role": "user", "content": "2"}])
    assert len(server.auth_calls) == 1


async def test_expiring_token_is_refreshed():
    server = FakeGigaChat(answers=[GOOD, GOOD], expires_in=30)  # истекает раньше, чем через минуту
    llm = llm_for(server)
    await llm.complete([{"role": "user", "content": "1"}])
    await llm.complete([{"role": "user", "content": "2"}])
    assert len(server.auth_calls) == 2


async def test_401_gets_new_token_once():
    server = FakeGigaChat(chat_status=[401, 200])
    reply = await llm_for(server).complete([{"role": "user", "content": "вопрос"}])
    assert reply.content == GOOD
    assert [c["auth"] for c in server.chat_calls] == ["Bearer token-1", "Bearer token-2"]


@pytest.mark.parametrize(
    "server",
    [
        FakeGigaChat(auth_status=401),  # неверный ключ
        FakeGigaChat(chat_status=429),  # у физлица один поток — второй параллельный запрос
        FakeGigaChat(chat_status=500),
        FakeGigaChat(chat_status=[401, 401]),
    ],
)
async def test_errors_are_llm_unavailable(server):
    with pytest.raises(LLMUnavailable):
        await llm_for(server).complete([{"role": "user", "content": "вопрос"}])


async def test_network_error_is_llm_unavailable():
    def boom(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMUnavailable):
        await GigaChatLLM(
            credentials="x", http_client=httpx.AsyncClient(transport=httpx.MockTransport(boom))
        ).complete([{"role": "user", "content": "вопрос"}])


async def test_ask_with_gigachat():
    """#76: каждое сообщение отвечает модель — её текст доходит до пользователя как есть."""
    server = FakeGigaChat()
    res = await ask(
        "Хочу купить телефон за 14 900 ₽", "impulse", load_demo_state(), DEMO_AS_OF, llm=llm_for(server)
    )
    assert res.result["text"] == GOOD
    system, user = server.chat_calls[0]["body"]["messages"][:2]
    assert system["role"] == "system" and "ФинРитм" in system["content"]
    assert "Проверка траты 14" in user["content"]


async def test_ask_raises_when_gigachat_down():
    """Модель недоступна — API ответит 503 «помощник временно недоступен», без подменного шаблона."""
    with pytest.raises(LLMUnavailable):
        await ask(
            "Хочу купить телефон за 14 900 ₽",
            "impulse",
            load_demo_state(),
            DEMO_AS_OF,
            llm=llm_for(FakeGigaChat(chat_status=429)),
        )


def test_factory(monkeypatch):
    monkeypatch.delenv("GIGACHAT_SCOPE", raising=False)
    llm = get_llm(SimpleNamespace(llm_provider="gigachat", gigachat_credentials="key", llm_model=""))
    assert isinstance(llm, GigaChatLLM)
    assert (llm.model, llm.scope, llm.answer_timeout) == ("GigaChat", "GIGACHAT_API_PERS", 40)
    llm = get_llm(
        SimpleNamespace(llm_provider="gigachat", gigachat_credentials="key", llm_model="GigaChat-2-Pro")
    )
    assert llm.model == "GigaChat-2-Pro"


def test_factory_needs_credentials(monkeypatch):
    monkeypatch.delenv("GIGACHAT_CREDENTIALS", raising=False)
    with pytest.raises(ValueError, match="GIGACHAT_CREDENTIALS"):
        get_llm(SimpleNamespace(llm_provider="gigachat", gigachat_credentials=""))


def test_russian_root_ca_is_bundled():
    assert "BEGIN CERTIFICATE" in CA_FILE.read_text(encoding="ascii")
    context = ssl_context()
    subjects = [dict(x[0] for x in c["subject"]).get("commonName") for c in context.get_ca_certs()]
    assert "Russian Trusted Root CA" in subjects
