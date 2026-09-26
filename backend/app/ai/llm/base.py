"""Общий интерфейс LLM-провайдеров.

Сообщения — в формате OpenAI Chat Completions: {"role": "system"|"user"|"assistant"|"tool", ...}.
Вызовы инструментов ассистента и результаты инструментов собираются через
assistant_message() и tool_message(), чтобы все провайдеры видели одинаковую историю.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMReply:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMUnavailable(RuntimeError):
    """Провайдер LLM не ответил: таймаут, сеть, ошибка сервера. API превращает в 503."""


class LLMClient(Protocol):
    name: str

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMReply: ...


def assistant_message(reply: LLMReply) -> dict:
    """Ответ модели (возможно, с вызовами инструментов) как сообщение истории."""
    message: dict[str, Any] = {"role": "assistant", "content": reply.content}
    if reply.tool_calls:
        message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)},
            }
            for call in reply.tool_calls
        ]
    return message


def tool_message(call: ToolCall, result: dict) -> dict:
    """Результат инструмента как сообщение истории."""
    return {
        "role": "tool",
        "tool_call_id": call.id,
        "name": call.name,
        "content": json.dumps(result, ensure_ascii=False),
    }
