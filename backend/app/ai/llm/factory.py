from __future__ import annotations

import logging
import os
from typing import Any

from app.ai.llm.base import LLMClient
from app.ai.llm.fake import FakeLLM
from app.ai.llm.openai_compat import DEFAULT_TIMEOUT, OpenAICompatLLM

log = logging.getLogger(__name__)

PROVIDERS = ("fake", "openai_compat")


def llm_timeout(settings: Any) -> float:
    """Бюджет на ответ модели, секунды: settings.llm_timeout или LLM_TIMEOUT из окружения, иначе 40."""
    raw = getattr(settings, "llm_timeout", None) or os.environ.get("LLM_TIMEOUT")
    try:
        value = float(raw) if raw else DEFAULT_TIMEOUT
    except (TypeError, ValueError):
        log.warning("LLM_TIMEOUT=%r — не число, беру %s с", raw, DEFAULT_TIMEOUT)
        return DEFAULT_TIMEOUT
    return value if value > 0 else DEFAULT_TIMEOUT


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
            base_url=base_url,
            model=model,
            api_key=getattr(settings, "llm_api_key", "") or "",
            timeout=llm_timeout(settings),
        )
    raise ValueError(
        f"Неизвестный LLM_PROVIDER={provider!r}. Доступно: {', '.join(PROVIDERS)}. "
        "Без ключа LLM используйте LLM_PROVIDER=fake."
    )
