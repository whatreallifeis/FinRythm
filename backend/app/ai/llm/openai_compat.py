"""OpenAI-совместимый провайдер: Ollama (qwen2.5:7b), OpenAI, YandexGPT-совместимый эндпоинт и другие.

Ошибки сети, таймаут и ошибки сервера → LLMUnavailable (API отвечает 503).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import openai

from app.ai.llm.base import LLMReply, LLMUnavailable, ToolCall

log = logging.getLogger(__name__)

# На CPU ответ 7B-модели идёт 10–40 с (docs/03_deploy.md), поэтому запасом.
DEFAULT_TIMEOUT = 45.0


class OpenAICompatLLM:
    name = "openai_compat"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = DEFAULT_TIMEOUT,
        temperature: float = 0.3,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.model = model
        self.temperature = temperature
        self._client = openai.AsyncOpenAI(
            base_url=base_url,
            # Ollama ключ не проверяет, но клиент openai требует непустую строку.
            api_key=api_key or "not-needed",
            timeout=timeout,
            max_retries=0,
            http_client=http_client,
        )

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMReply:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": self.temperature}
        if tools:
            kwargs["tools"] = tools
        try:
            response = await self._client.chat.completions.create(**kwargs)
        except (openai.APIConnectionError, openai.APITimeoutError) as error:
            log.warning("llm unreachable: %s", type(error).__name__)
            raise LLMUnavailable("Модель не отвечает") from error
        except openai.APIStatusError as error:
            log.warning("llm error status=%s", error.status_code)
            raise LLMUnavailable(f"Модель вернула ошибку {error.status_code}") from error
        if not response.choices:
            raise LLMUnavailable("Модель вернула пустой ответ")
        message = response.choices[0].message
        calls = [
            ToolCall(id=call.id, name=call.function.name, arguments=_arguments(call.function.arguments))
            for call in (message.tool_calls or [])
        ]
        return LLMReply(content=message.content, tool_calls=calls)


def _arguments(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
