"""Точка входа помощника для POST /api/ask (сценарии ruina696, origin/front:docs/ai-scenarios.md).

API передаёт вопрос, scenarioId и данные пользователя, получает Explained с result = {"text": ...}.
Порядок: фильтр рискованных запросов (до расчётов и LLM) → сценарий → текст вокруг чисел app.core →
проверка чисел: каждое число в тексте должно быть в результатах расчёта, вопросе или источнике.
"""

from __future__ import annotations

import datetime as dt
import logging

from app.ai import guardrails, scenarios
from app.ai.amounts import extract_amount
from app.ai.llm.base import LLMClient
from app.ai.number_check import allowed_numbers, check_numbers
from app.ai.tools import KnowledgeSearch
from app.models import SCENARIO_IDS, Explained, ScenarioId, UserState

log = logging.getLogger(__name__)

DECIDE_PREFIX = "Решать вам — я покажу последствия."


def verify_numbers(reply: scenarios.Reply, question: str) -> tuple[bool, list]:
    """Числа ответа против результатов расчёта, вопроса и источников."""
    allowed = allowed_numbers(reply.explained, question=question, facts=reply.facts)
    return check_numbers(reply.explained.result.get("text", ""), allowed)


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
    if intent is not None and not (intent == "decide_for_me" and extract_amount(question) is not None):
        return guardrails.refusal(intent, state, as_of, kb)

    # «Реши за меня, покупать ли за 4 900 ₽» — показываем последствия покупки, решение за пользователем.
    decide = intent == "decide_for_me"
    reply = scenarios.run_reply("impulse" if decide else scenario_id, question, state, as_of, kb)
    ok, bad = verify_numbers(reply, question)
    if not ok:
        # Шаблоны берут числа только из core — расхождение значит ошибку в шаблоне, её видно в логах.
        log.warning("number check failed: scenario=%s numbers=%s", scenario_id, [str(n) for n in bad])
    if decide and reply.explained.data_quality.sufficient:
        reply.explained.result["text"] = f"{DECIDE_PREFIX} {reply.explained.result['text']}"
    return reply.explained
