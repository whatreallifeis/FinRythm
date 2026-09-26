from __future__ import annotations

from typing import Any

from app.ai.llm.base import LLMClient
from app.ai.llm.fake import FakeLLM

PROVIDERS = ("fake",)


def get_llm(settings: Any) -> LLMClient:
    """LLM-клиент по настройке LLM_PROVIDER (settings.llm_provider)."""
    provider = (getattr(settings, "llm_provider", None) or "fake").strip().lower()
    if provider == "fake":
        return FakeLLM()
    raise ValueError(
        f"Неизвестный LLM_PROVIDER={provider!r}. Доступно: {', '.join(PROVIDERS)}. "
        "Без ключа LLM используйте LLM_PROVIDER=fake."
    )
