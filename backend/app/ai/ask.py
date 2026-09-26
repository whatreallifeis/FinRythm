"""Точка входа помощника для POST /api/ask (сценарии ruina696, origin/front:docs/ai-scenarios.md).

API передаёт вопрос, scenarioId и данные пользователя, получает Explained с result = {"text": ...}.
Порядок:
1. Фильтр рискованных запросов — до расчётов и до модели.
2. Сценарий: расчёты app.core и шаблонный текст вокруг их чисел.
3. Если подключена модель (LLM_PROVIDER=openai_compat) и данных хватает — модель переписывает шаблон.
4. Проверка чисел: каждое число текста должно быть в расчёте, вопросе или источнике. Провал — одна
   повторная попытка с подсказкой, затем шаблонный текст. Модель не ответила вовремя — LLMUnavailable (503).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
import time

from app.ai import guardrails, prompts, scenarios
from app.ai.amounts import extract_amount
from app.ai.llm.base import LLMClient, LLMUnavailable
from app.ai.number_check import allowed_numbers, check_numbers
from app.ai.tools import KnowledgeSearch
from app.core.money import fmt_rub
from app.models import SCENARIO_IDS, Explained, ScenarioId, UserState

log = logging.getLogger(__name__)

DECIDE_PREFIX = "Решать вам — я покажу последствия."
# Весь ответ модели, включая повторную попытку. На CPU 7B-модель отвечает 10–40 с (docs/03_deploy.md).
ANSWER_TIMEOUT = 60.0
MAX_ATTEMPTS = 2
MAX_TEXT = 1500


def verify_numbers(reply: scenarios.Reply, question: str, text: str | None = None) -> tuple[bool, list]:
    """Числа ответа против результатов расчёта, вопроса и источников."""
    allowed = allowed_numbers(reply.explained, question=question, facts=reply.facts)
    return check_numbers(reply.explained.result.get("text", "") if text is None else text, allowed)


def uses_model(llm: LLMClient | None) -> bool:
    return llm is not None and getattr(llm, "name", "fake") != "fake"


def _clean(text: str | None) -> str:
    text = (text or "").strip()
    if len(text) > 1 and text[0] + text[-1] in ('""', "''", "«»"):  # модель обернула весь ответ в кавычки
        text = text[1:-1].strip()
    # Схлопываем переносы и обычные пробелы; неразрывный пробел в «14 900 ₽» оставляем.
    return re.sub(r"[ \t\r\n]+", " ", text)[:MAX_TEXT]


async def rewrite(
    llm: LLMClient, scenario_id: str, question: str, reply: scenarios.Reply, today: dt.date
) -> str:
    """Текст модели, прошедший проверку чисел, или шаблонный текст. Таймаут и сбой — LLMUnavailable."""
    draft = reply.explained.result["text"]
    messages = [
        {"role": "system", "content": prompts.system_prompt(scenario_id, today)},
        {"role": "user", "content": prompts.user_message(question, reply.facts, draft)},
    ]
    deadline = time.monotonic() + ANSWER_TIMEOUT
    for attempt in range(1, MAX_ATTEMPTS + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            answer = await asyncio.wait_for(llm.complete(messages), timeout=remaining)
        except TimeoutError as error:
            if attempt == 1:
                raise LLMUnavailable("Модель не ответила вовремя") from error
            break  # на повторной попытке — просто шаблон
        text = _clean(answer.content)
        if not re.search(r"[а-яё]", text, re.IGNORECASE):
            hint = prompts.NOT_RUSSIAN
        else:
            ok, bad = verify_numbers(reply, question, text)
            if ok:
                return text
            hint = prompts.RETRY.format(numbers=", ".join(str(n) for n in bad))
        log.warning("llm answer rejected: scenario=%s attempt=%d reason=%s", scenario_id, attempt, hint[:40])
        messages += [{"role": "assistant", "content": text}, {"role": "user", "content": hint}]
    log.warning("llm template fallback: scenario=%s", scenario_id)
    return draft


def not_buying_text(reply: scenarios.Reply) -> str:
    """«Если не покупать…» из того же расчёта покупки (§7.3: последствия обоих вариантов)."""
    check = next((f for f in reply.facts if isinstance(f, dict) and "todaySafeSpendBefore" in f), None)
    if check is None:
        return ""
    red = check.get("redDaysBefore") or 0
    days = "дней в минусе не будет" if not red else f"дней в минусе: {red}"
    return f" Если не покупать — можно тратить {fmt_rub(check['todaySafeSpendBefore'])} в день, {days}."


async def ask(
    question: str,
    scenario_id: ScenarioId,
    state: UserState,
    as_of: dt.date,
    *,
    llm: LLMClient | None = None,
    kb: KnowledgeSearch | None = None,
) -> Explained:
    """Ответ помощника на вопрос пользователя в сценарии scenario_id."""
    if scenario_id not in SCENARIO_IDS:
        raise ValueError(f"Неизвестный сценарий {scenario_id!r}. Доступны: {', '.join(SCENARIO_IDS)}.")

    intent = guardrails.classify_risky(question)
    decide = intent == "decide_for_me" and extract_amount(question) is not None
    if intent is not None and not decide:
        return guardrails.refusal(intent, state, as_of, kb)

    # «Реши за меня, покупать ли за 4 900 ₽» — последствия обоих вариантов, решение за пользователем.
    run_scenario = "impulse" if decide else scenario_id
    reply = scenarios.run_reply(run_scenario, question, state, as_of, kb)
    if not reply.explained.data_quality.sufficient:
        return reply.explained
    if decide:
        reply.explained.result["text"] = (
            f"{DECIDE_PREFIX} {reply.explained.result['text']}{not_buying_text(reply)}"
        )

    ok, bad = verify_numbers(reply, question)
    if not ok:
        # Шаблоны берут числа только из core — расхождение значит ошибку в шаблоне, её видно в логах.
        log.warning("number check failed: scenario=%s numbers=%s", scenario_id, [str(n) for n in bad])

    if uses_model(llm):
        effective = run_scenario
        if effective == "free":  # промпт — того сценария, который выбрал classify_free
            effective = scenarios.classify_free(question) or "free"
        reply.explained.result["text"] = await rewrite(llm, effective, question, reply, as_of)
    return reply.explained
