"""Точка входа помощника для POST /api/ask (сценарии ruina696, origin/front:docs/ai-scenarios.md).

API передаёт вопрос, scenarioId и данные пользователя, получает Explained с result = {"text": ...}.
Числа в ответе считает только app.core; здесь — выбор сценария и текст вокруг готовых чисел.
"""

from __future__ import annotations

import datetime as dt

from app.ai import scenarios
from app.ai.llm.base import LLMClient
from app.ai.tools import KnowledgeSearch
from app.models import SCENARIO_IDS, Explained, ScenarioId, UserState


async def ask(
    question: str,
    scenario_id: ScenarioId,
    state: UserState,
    as_of: dt.date,
    *,
    llm: LLMClient | None = None,
    kb: KnowledgeSearch | None = None,
) -> Explained:
    """Ответ помощника на вопрос пользователя в сценарии scenario_id.

    Сейчас текст собирается по шаблонам (режим fake); реальный LLM подключается в AF5.
    """
    if scenario_id not in SCENARIO_IDS:
        raise ValueError(f"Неизвестный сценарий {scenario_id!r}. Доступны: {', '.join(SCENARIO_IDS)}.")
    return scenarios.run(scenario_id, question, state, as_of, kb)
