"""GigaChat API (Сбер): бесплатный Freemium для физлиц, работает с серверов в России.

Отличия от OpenAI-совместимого API:
- доступ по токену, который выдаёт сервер авторизации по ключу GIGACHAT_CREDENTIALS; токен живёт 30 минут;
- сертификаты серверов выданы Минцифры (Russian Trusted Root CA) — корневой сертификат лежит рядом,
  проверку TLS не отключаем.

Ошибки сети, таймаут, отказ в доступе и ошибки сервера → LLMUnavailable: ask() отдаёт шаблонный ответ.
"""

from __future__ import annotations

import logging
import ssl
import time
import uuid
from pathlib import Path
from typing import Any

import certifi
import httpx

from app.ai.llm.base import LLMReply, LLMUnavailable
from app.ai.llm.openai_compat import DEFAULT_MAX_TOKENS, DEFAULT_TIMEOUT

log = logging.getLogger(__name__)

AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API_URL = "https://gigachat.devices.sberbank.ru/api/v1"
# GIGACHAT_API_PERS — физлица (Freemium); GIGACHAT_API_B2B / _CORP — юрлица.
DEFAULT_SCOPE = "GIGACHAT_API_PERS"
DEFAULT_MODEL = "GigaChat"
CA_FILE = Path(__file__).parent / "certs" / "russian_trusted_root_ca.pem"
# Обновляем токен заранее, чтобы он не истёк посреди запроса.
TOKEN_MARGIN_SECONDS = 60


def ssl_context(ca_file: Path = CA_FILE) -> ssl.SSLContext:
    """Обычные корневые сертификаты + сертификат Минцифры."""
    context = ssl.create_default_context(cafile=certifi.where())
    context.load_verify_locations(cafile=str(ca_file))
    return context


class GigaChatLLM:
    name = "gigachat"

    def __init__(
        self,
        *,
        credentials: str,
        scope: str = DEFAULT_SCOPE,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        temperature: float = 0.2,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.model = model
        self.scope = scope
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.answer_timeout = timeout  # ask() укладывает в него весь ответ вместе с повтором
        self._credentials = credentials
        self._client = http_client or httpx.AsyncClient(verify=ssl_context(), timeout=timeout)
        self._token: str | None = None
        self._token_expires = 0.0

    async def _access_token(self, *, refresh: bool = False) -> str:
        if not refresh and self._token and time.time() < self._token_expires - TOKEN_MARGIN_SECONDS:
            return self._token
        try:
            response = await self._client.post(
                AUTH_URL,
                headers={
                    "Authorization": f"Basic {self._credentials}",
                    "RqUID": str(uuid.uuid4()),
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={"scope": self.scope},
            )
        except httpx.HTTPError as error:
            log.warning("gigachat auth unreachable: %s", type(error).__name__)
            raise LLMUnavailable("GigaChat: сервер авторизации не отвечает") from error
        if response.status_code != 200:
            log.warning("gigachat auth status=%s", response.status_code)
            raise LLMUnavailable(f"GigaChat: авторизация не прошла ({response.status_code})")
        data = response.json()
        self._token = data["access_token"]
        # expires_at — миллисекунды с 1970 года
        self._token_expires = float(data.get("expires_at", 0)) / 1000 or time.time() + 30 * 60
        return self._token

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMReply:
        """Инструменты (tools) GigaChat задаёт в своём формате; ask() их не использует — не передаём."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        for attempt in (1, 2):
            token = await self._access_token(refresh=attempt == 2)
            try:
                response = await self._client.post(
                    f"{API_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    json=payload,
                )
            except httpx.HTTPError as error:
                log.warning("gigachat unreachable: %s", type(error).__name__)
                raise LLMUnavailable("GigaChat не отвечает") from error
            if response.status_code == 401 and attempt == 1:
                continue  # токен отозван раньше срока — берём новый
            if response.status_code != 200:
                log.warning("gigachat error status=%s", response.status_code)
                raise LLMUnavailable(f"GigaChat вернул ошибку {response.status_code}")
            choices = response.json().get("choices") or []
            if not choices:
                raise LLMUnavailable("GigaChat вернул пустой ответ")
            return LLMReply(content=choices[0].get("message", {}).get("content"))
        raise LLMUnavailable("GigaChat: авторизация не прошла")
