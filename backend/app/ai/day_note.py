"""Справка помощника по дню календаря: GigaChat переписывает шаблон живым языком.

Числа справки посчитал core (app.core.day). Модель получает шаблон и может только пересказать его;
проверка чисел сверяет ответ с расчётом дня. Не прошла проверку, не успела, нет сети — остаётся шаблон:
справка должна открываться сразу, поэтому повтора нет и время ограничено.
"""

from __future__ import annotations

import asyncio
import logging

from app.ai.analyst import clean, informal_problem, junk_problem, label_problem
from app.ai.answer_check import language_problem
from app.ai.llm.base import LLMClient, LLMUnavailable
from app.ai.number_check import allowed_numbers, check_numbers
from app.models import Explained

log = logging.getLogger(__name__)

NOTE_TIMEOUT = 12.0

SYSTEM = """Ты — финансовый помощник для студентов. Пиши только по-русски, на «вы», 2–4 предложения
обычного текста без списков и разметки. Тебе дан черновик справки о регулярных платежах одного дня —
его числа посчитала программа. Перескажи черновик понятнее: что это за платёж или поступление,
менялась ли сумма, что это значит для бюджета. Бери числа, даты и названия только из черновика
и в том же виде («12 000 ₽»); ничего не считай и не добавляй новых фактов, догадок и советов.
«За год выходит …» — это прогноз на будущее, а не уже потраченные деньги: не превращай его в факт.
Доля «регулярных расходов» — не доля всех трат: сохраняй, от чего считается процент."""


async def polish(llm: LLMClient, insight: Explained) -> Explained:
    """Та же справка, но текст справки — от модели, если он прошёл проверку."""
    draft = insight.result.get("note")
    if not draft:
        return insight
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Черновик справки:\n{draft}"},
    ]
    timeout = min(float(getattr(llm, "answer_timeout", NOTE_TIMEOUT) or NOTE_TIMEOUT), NOTE_TIMEOUT)
    try:
        answer = await asyncio.wait_for(llm.complete(messages), timeout=timeout)
    except (TimeoutError, LLMUnavailable) as error:
        log.warning("day note llm unavailable: %s", type(error).__name__)
        return insight
    text = clean(answer.content)
    problem = (
        language_problem(text, [draft]) or informal_problem(text) or label_problem(text) or junk_problem(text)
        if text
        else "пустой ответ"
    )
    if problem is None:
        ok, bad = check_numbers(text, allowed_numbers(insight, facts=[draft]))
        problem = None if ok else f"чужие числа: {', '.join(str(n) for n in bad)}"
    if problem:
        log.warning("day note rejected: %s", problem[:80])
        return insight
    result = {**insight.result, "note": text}
    assumptions = [
        *insight.assumptions,
        "Текст справки сформулировала нейросеть GigaChat; числа в нём сверены с расчётом дня.",
    ]
    return insight.model_copy(update={"result": result, "assumptions": assumptions})
