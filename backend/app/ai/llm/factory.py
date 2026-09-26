from __future__ import annotations

from typing import Any

from app.ai.llm.base import LLMClient
from app.ai.llm.fake import FakeLLM
from app.ai.llm.openai_compat import OpenAICompatLLM

PROVIDERS = ("fake", "openai_compat")


def get_llm(settings: Any) -> LLMClient:
    """LLM-клиент по настройке LLM_PROVIDER (settings.llm_provider)."""
    provider = (getattr(settings, "llm_provider", None) or "fake").strip().lower()
    if provider == "fake":
        return FakeLLM()
    if provider == "openai_compat":
        base_url = (getattr(settings, "llm_base_url", "") or "").strip()
        model = (getattr(settings, "llm_model", "") or "").strip()
        missing = [name for name, value in (("LLM_BASE_URL", base_url), ("LLM_MODEL", model)) if not value]
        if missing:
            raise ValueError(
                f"Для LLM_PROVIDER=openai_compat задайте {', '.join(missing)} "
                "(например, Ollama: LLM_BASE_URL=http://localhost:11434/v1, LLM_MODEL=qwen2.5:7b)."
            )
        return OpenAICompatLLM(
            base_url=base_url, model=model, api_key=getattr(settings, "llm_api_key", "") or ""
        )
    raise ValueError(
        f"Неизвестный LLM_PROVIDER={provider!r}. Доступно: {', '.join(PROVIDERS)}. "
        "Без ключа LLM используйте LLM_PROVIDER=fake."
    )
