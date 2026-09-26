"""Точка входа помощника для POST /api/ask (сценарии ruina696, origin/front:docs/ai-scenarios.md).

API передаёт вопрос, scenarioId и данные пользователя, получает Explained с result = {"text": ...}.
Порядок: фильтр рискованных запросов (до расчётов и LLM) → сценарий → текст вокруг чисел app.core.
"""

from __future__ import annotations

import datetime as dt

from app.ai import guardrails, scenarios
from app.ai.amounts import extract_amount
from app.ai.llm.base import LLMClient
from app.ai.tools import KnowledgeSearch
from app.models import SCENARIO_IDS, Explained, ScenarioId, UserState

DECIDE_PREFIX = "Решать вам — я покажу последствия."


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

    intent = guardrails.classify_risky(question)
    if intent == "decide_for_me" and extract_amount(question) is not None:
        # «Реши за меня, покупать ли за 4 900 ₽» — показываем последствия покупки, решение за пользователем.
        res = scenarios.run("impulse", question, state, as_of, kb)
        if res.data_quality.sufficient:
            res.result["text"] = f"{DECIDE_PREFIX} {res.result['text']}"
        return res
    if intent is not None:
        return guardrails.refusal(intent, state, as_of, kb)
    return scenarios.run(scenario_id, question, state, as_of, kb)
