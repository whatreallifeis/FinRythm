"""Точка входа помощника для POST /api/ask.

С моделью (LLM_PROVIDER=gigachat и др.) каждое сообщение отвечает модель — app.ai.chat: она получает данные
пользователя, посчитанные app.core, и справку из базы знаний; заготовленных ответов нет (#76).
Без модели (LLM_PROVIDER=fake, тесты) — сценарии по шаблонам: фильтр рискованных запросов, расчёты app.core
и текст вокруг их чисел.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from decimal import Decimal

from app.ai import chat, guardrails, scenarios
from app.ai.amounts import extract_amount
from app.ai.llm.base import LLMClient
from app.ai.number_check import allowed_numbers, check_numbers
from app.ai.tools import KnowledgeSearch
from app.core.money import fmt_num, fmt_rub
from app.models import SCENARIO_IDS, Explained, ScenarioId, UserState

log = logging.getLogger(__name__)

DECIDE_PREFIX = "Решать вам — я покажу последствия."
# Бюджет на весь ответ модели, включая повторную попытку (у клиента можно задать answer_timeout).
ANSWER_TIMEOUT = 40.0
# Повторная попытка — только если до конца бюджета осталось хотя бы столько.
MIN_RETRY_SECONDS = 12.0
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
    return tidy_numbers(re.sub(r"[ \t\r\n]+", " ", text)[:MAX_TEXT])


_MINUS = re.compile(r"(?<![\w\d])-(?=\d)")
# Суммы без разделителя разрядов: «10618 ₽» или длинные числа от 5 знаков. Годы («2027 года») не трогаем.
_UNGROUPED = re.compile(r"(?<![\w.,])(\d{4})(?=\s?₽)|(?<![\w.,])(\d{5,})(?![\w.,])")


def tidy_numbers(text: str) -> str:
    """Числа модели — в том же виде, что в шаблонах: «-10618 ₽» → «−10 618 ₽»."""

    def group(match: re.Match[str]) -> str:
        return fmt_num(Decimal(match.group(1) or match.group(2)))

    return _UNGROUPED.sub(group, _MINUS.sub("−", text))


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

    if uses_model(llm):
        # Любое сообщение — модели: один собеседник, без заготовленных ответов (#76).
        return await chat.answer(question, scenario_id, state, as_of, llm=llm, kb=kb)

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

    return reply.explained
