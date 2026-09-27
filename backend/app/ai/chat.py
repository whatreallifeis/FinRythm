"""Помощник — один ИИ-собеседник: каждое сообщение отвечает модель (решение Вероники, #76).

Никаких заготовленных ответов: приветствие, вопрос про деньги, термин, рискованная просьба — всё
обрабатывает модель. Код делает то, что модели доверять нельзя:
- считает (app.core) и передаёт модели готовые данные пользователя — баланс, календарь до поступления,
  траты по категориям, цели, проверку покупки, если в сообщении есть сумма;
- находит справку в проверенной базе знаний — модель ссылается на неё, а не на память;
- прячет номера карт до отправки сообщения во внешний сервис;
- проверяет ответ: чужие числа и иностранные слова → повтор с подсказкой.
Правила (не советовать вложения и кредиты, не решать за пользователя) — в системном промпте.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
import time
from decimal import Decimal
from typing import Any

from app.ai import core_calls, guardrails, scenarios
from app.ai.amounts import extract_amount
from app.ai.answer_check import language_problem
from app.ai.core_calls import CoreNotReady
from app.ai.llm.base import LLMClient, LLMUnavailable
from app.ai.number_check import allowed_numbers, check_numbers
from app.ai.tools import KnowledgeSearch
from app.core.money import days_word, fmt_rub
from app.models import CalcStep, DataQuality, Explained, SourceRef, UserState

log = logging.getLogger(__name__)

ANSWER_TIMEOUT = 40.0
MIN_RETRY_SECONDS = 8.0
MAX_ATTEMPTS = 3
MAX_TEXT = 2500
RECENT_OPERATIONS = 30

SECTIONS = {
    "expenses": "Анализ трат",
    "budget": "Бюджет до конца месяца",
    "glossary": "Справочник терминов",
    "impulse": "Могу купить это сегодня?",
    "free": "Свой вопрос",
}

SYSTEM = """Ты — ФинРитм, дружелюбный помощник по личным финансам для студентов. Общайся по-русски, на «вы»,
живо и по делу. Отвечай на любое сообщение пользователя: на приветствие — приветствием, на вопрос — ответом.
Тебе переданы данные пользователя, посчитанные программой. Все суммы, проценты и даты бери только из них,
в том же виде («18 430 ₽»). Сам ничего не считай: не складывай, не вычитай, не выводи итогов и процентов,
которых нет в данных, — если нужен итог, которого нет, перечисли суммы без итога. Не утверждай, что денег
хватит или не хватит, если этого нет в данных. Если нужных данных нет — так и скажи и подскажи, что загрузить.
Термины объясняй по справке из проверенного источника, если она передана, и называй источник.
Не советуй, куда вложить деньги (ни вклады, ни акции, ни криптовалюту), не советуй кредиты, займы и ставки,
не решай за пользователя и не проводи операций с деньгами: вежливо объясни, что это финансовая рекомендация,
которую даёт только лицензированный консультант, и предложи, чем можешь помочь по его бюджету.
Не проси и не повторяй номера карт, CVV и коды из СМС. Пиши обычным текстом: без таблиц, звёздочек
и другой разметки, до 6 предложений."""

RETRY_NUMBERS = (
    "В ответе числа, которых нет в данных: {numbers}. Перепиши ответ, беря числа только из данных, "
    "и ничего не считай сам."
)
RETRY_LANGUAGE = "Перепиши ответ только по-русски: {problem}."
RETRY_ADVICE = (
    "Ты посоветовал, куда вложить деньги или взять кредит, — так нельзя: это финансовая рекомендация, "
    "её даёт только лицензированный консультант. Перепиши ответ без советов по продуктам (вклады, акции, "
    "криптовалюта, кредиты, займы) и предложи помочь с бюджетом по данным пользователя."
)

# Вопрос про вложения, кредиты, ставки — ответ не должен советовать продукт (правила кейса, §7.3 ТЗ).
_ADVICE_INTENTS = {"investment", "crypto", "credit", "gambling"}
_ADVICE = re.compile(
    r"рассмотр(?:ите|еть)|рекоменд(?:ую|уем)|совету(?:ю|ем)|"
    r"(?:стоит|лучше|можно|следует) "
    r"(?:открыть|вложить|взять|купить|выбрать|инвестировать|оформить|изучить|присмотреться)|"
    r"открой(?:те)? (?:вклад|счёт|счет)|купи(?:те)? акци|вложи(?:те)?\b",
    re.IGNORECASE,
)


def advice_problem(question: str, text: str) -> bool:
    """На вопрос о вложениях/кредитах/ставках модель всё же посоветовала продукт."""
    return guardrails.classify_risky(question) in _ADVICE_INTENTS and bool(_ADVICE.search(text))


_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def mask_personal(text: str) -> str:
    """Номер карты не должен уйти во внешний сервис."""
    return _CARD.sub("[номер карты скрыт]", text)


def _pct(share: Any) -> str:
    return scenarios.fmt_pct(share)


def build_context(
    question: str, scenario_id: str, state: UserState, as_of: dt.date, kb: KnowledgeSearch | None
) -> tuple[str, list[Explained], list[Any], list[SourceRef]]:
    """(текст данных для модели, результаты core, факты для проверки чисел, источники)."""
    lines: list[str] = [f"Сегодня: {scenarios.human_date(as_of)} {as_of.year} года."]
    parts: list[Explained] = []
    facts: list[Any] = []
    sources: list[SourceRef] = []

    lines.append(
        f"Баланс на счёте: {fmt_rub(state.balance)}." if state.balance is not None else "Баланс не указан."
    )
    if state.incomes:
        incomes = "; ".join(
            f"{i.title} — {fmt_rub(i.amount)} {i.day_of_month}-го числа" for i in state.incomes
        )
        lines.append(f"Регулярные поступления: {incomes}.")
    else:
        lines.append("Регулярные поступления не указаны.")

    def call(name: str, *args: Any) -> Explained | None:
        try:
            res = getattr(core_calls, name)(*args)
        except CoreNotReady:
            return None
        if res is None:
            return None
        if not res.data_quality.sufficient:
            if res.data_quality.missing:
                lines.append(f"Нет данных для расчёта ({name}): {', '.join(res.data_quality.missing)}.")
            return None
        parts.append(res)
        facts.append(res.result)
        return res

    if runway := call("runway", state, as_of):
        r = runway.result
        if nxt := r.get("nextIncome"):
            lines.append(
                f"Ближайшее поступление: «{nxt['title']}» {fmt_rub(nxt['amount'])} "
                f"{scenarios.human_date(nxt['date'])}, через {days_word(nxt['daysUntil'])}."
            )
        lines.append(
            f"Можно безопасно тратить {fmt_rub(r['todaySafeSpend'])} в день до поступления; "
            f"минимальный остаток в календаре — {fmt_rub(r['lowestBalance'])}; дней в минусе: {r['redDays']}."
        )
        payments = [
            f"{scenarios.human_date(d['date'])}: {e['title']} {fmt_rub(e['amount'])}"
            for d in r.get("days", [])
            for e in d.get("events", [])
            if Decimal(str(e["amount"])) < 0
        ]
        if payments:
            lines.append("Обязательные платежи впереди: " + "; ".join(payments[:12]) + ".")

    if forecast := call("forecast", state, as_of):
        f = forecast.result
        lines.append(
            f"Прогноз до конца месяца ({days_word(f['daysLeft'])}): ожидается поступлений "
            f"{fmt_rub(f['expectedIncome'])}, обязательных трат {fmt_rub(f['plannedExpenses'])}, "
            f"останется {fmt_rub(f['projectedBalance'])}, "
            f"можно тратить {fmt_rub(f['safeDailySpend'])} в день."
        )

    if state.transactions and (overview := call("overview", state, as_of)):
        o = overview.result
        cats = "; ".join(
            f"{scenarios.label(c['category'])} — {fmt_rub(c['amount'])} ({_pct(c['share'])})"
            + (
                f", к прошлому месяцу {c['deltaPercent']:+}%"
                if c.get("deltaPercent") not in (None, 0)
                else ""
            )
            for c in o.get("byCategory", [])
        )
        lines.append(
            f"Расходы с {scenarios.human_date(o['periodFrom'])} по {scenarios.human_date(o['periodTo'])}: "
            f"всего {fmt_rub(o['totalExpense'])}, доходы {fmt_rub(o['totalIncome'])}, "
            f"регулярные платежи {fmt_rub(o['recurringTotal'])}. По категориям: {cats}."
        )
        if o.get("anomalies"):
            lines.append("Необычные траты: " + "; ".join(a["reason"] for a in o["anomalies"]) + ".")

    if state.transactions:
        recent = sorted(state.transactions, key=lambda op: (op.date, op.id), reverse=True)[:RECENT_OPERATIONS]
        ops = "; ".join(
            f"{scenarios.human_date(op.date)} {op.merchant or 'без описания'} {fmt_rub(op.amount)} "
            f"({scenarios.label(op.category)}{', регулярный' if op.is_recurring else ''})"
            for op in recent
        )
        lines.append(f"Последние операции: {ops}.")
        facts.append([{"amount": str(op.amount)} for op in recent])
    else:
        lines.append("Операций не загружено.")

    for goal in state.goals:
        text = (
            f"Цель «{goal.title}»: нужно {fmt_rub(goal.target_amount)}, "
            f"накоплено {fmt_rub(goal.saved_amount)}"
        )
        text += (
            f", срок {scenarios.human_date(goal.deadline)} {goal.deadline.year} года"
            if goal.deadline
            else ", без срока"
        )
        if goal.deadline and (plan := call("goal_plan", state, goal.id, as_of)):
            p = plan.result
            text += f"; чтобы успеть, откладывать около {fmt_rub(p['monthlyPace'])} в месяц"
        lines.append(text + ".")
    if not state.goals:
        lines.append("Целей накопления нет.")

    amount = extract_amount(question)
    if amount is not None and amount > 0 and (check := call("impulse", state, amount, as_of)):
        c = check.result
        text = (
            f"Проверка траты {fmt_rub(amount)} сегодня: {c['hint']} Лимит в день до — "
            f"{fmt_rub(c['todaySafeSpendBefore'])}, после — {fmt_rub(c['todaySafeSpendAfter'])}; "
            f"минимальный остаток после — {fmt_rub(c['lowestBalanceAfter'])}; "
            f"дней в минусе после — {c['redDaysAfter']}."
        )
        if wait := c.get("waitUntil"):
            text += f" Безопаснее после поступления «{wait['title']}» {scenarios.human_date(wait['date'])}."
        if impact := c.get("goalImpact"):
            text += f" Цель «{impact['goalTitle']}» отодвинется примерно на {impact['delayDays']} дн."
        lines.append(text)

    if kb is not None:
        for item in kb.search(question, k=2):
            frag = scenarios._fragment(item)
            title = frag.get("source_title") or frag["title"]
            text = f"Справка «{frag['title']}» (источник: {title}, {frag['url']}): {frag['text']}"
            if frag.get("mistake"):
                text += f" Типичная ошибка: {frag['mistake']}"
            lines.append(text)
            facts.append([frag["text"], frag.get("mistake") or ""])
            sources.append(SourceRef(title=title, url=frag["url"]))

    context = "\n".join(lines)
    facts.append(context)
    return context, parts, facts, sources


_MARKDOWN = re.compile(r"\*\*|__|^#+\s*|`", re.MULTILINE)
_SENTENCE = re.compile(r"(?<=[.!?…])\s+|\n+")


def _clean(text: str | None) -> str:
    """Обычный текст: фронтенд не рисует разметку — «**2 738 ₽**» показался бы со звёздочками."""
    text = _MARKDOWN.sub("", (text or "").strip())
    if len(text) > 1 and text[0] + text[-1] in ('""', "''", "«»"):
        text = text[1:-1].strip()
    return re.sub(r"[ \t]+", " ", text)[:MAX_TEXT].strip()


def drop_invented(text: str, allowed: set[Decimal]) -> str:
    """Убирает из ответа предложения с числами, которых нет в данных; остальной текст модели остаётся."""
    kept = [part for part in _SENTENCE.split(text) if part.strip() and check_numbers(part, allowed)[0]]
    return " ".join(kept).strip()


async def answer(
    question: str,
    scenario_id: str,
    state: UserState,
    as_of: dt.date,
    *,
    llm: LLMClient,
    kb: KnowledgeSearch | None = None,
) -> Explained:
    """Ответ модели на любое сообщение. Модель недоступна — LLMUnavailable (API отвечает 503)."""
    safe_question = mask_personal(question)
    context, parts, facts, sources = build_context(safe_question, scenario_id, state, as_of, kb)
    section = SECTIONS.get(scenario_id, SECTIONS["free"])
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": f"Раздел приложения: «{section}».\nДанные пользователя:\n{context}\n\n"
            f"Сообщение пользователя: {safe_question}",
        },
    ]
    explained_for_check = Explained(result={}, data_quality=DataQuality(sufficient=True))
    allowed = allowed_numbers(explained_for_check, question=safe_question, facts=facts)

    budget = float(getattr(llm, "answer_timeout", None) or ANSWER_TIMEOUT)
    deadline = time.monotonic() + budget
    text = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        remaining = deadline - time.monotonic()
        if attempt > 1 and remaining < MIN_RETRY_SECONDS:
            break
        try:
            reply = await asyncio.wait_for(llm.complete(messages), timeout=remaining)
        except TimeoutError as error:
            if text:
                break
            raise LLMUnavailable("Модель не ответила вовремя") from error
        except LLMUnavailable:
            if text:
                break
            raise
        text = _clean(reply.content) or text
        if not text:
            continue
        if problem := language_problem(text, [safe_question, context]):
            hint = RETRY_LANGUAGE.format(problem=problem)
        elif advice_problem(safe_question, text):
            hint = RETRY_ADVICE
        else:
            ok, bad = check_numbers(text, allowed)
            if ok:
                break
            hint = RETRY_NUMBERS.format(numbers=", ".join(str(n) for n in bad))
        log.warning("chat answer rejected: scenario=%s attempt=%d reason=%s", scenario_id, attempt, hint[:60])
        messages += [{"role": "assistant", "content": text}, {"role": "user", "content": hint}]
    if not text:
        raise LLMUnavailable("Модель вернула пустой ответ")
    if not language_problem(text, [safe_question, context]) and not check_numbers(text, allowed)[0]:
        # После всех попыток модель всё ещё называет числа, которых нет в данных: такие фразы не показываем.
        log.warning("chat: invented numbers dropped: scenario=%s", scenario_id)
        text = drop_invented(text, allowed) or text
    if advice_problem(safe_question, text):
        # Модель так и не убрала совет по вложениям/кредитам: фразы с советом не показываем.
        log.warning("chat: product advice dropped: scenario=%s", scenario_id)
        kept = [part for part in _SENTENCE.split(text) if part.strip() and not _ADVICE.search(part)]
        text = " ".join(kept).strip() or text

    calculation: list[CalcStep] = []
    for step in (s for p in parts for s in p.calculation):
        if all((step.label, step.value) != (seen.label, seen.value) for seen in calculation):
            calculation.append(step)
    assumptions = scenarios._dedupe([a for p in parts for a in p.assumptions])[:6]
    limitations = scenarios._dedupe([lim for p in parts for lim in p.limitations]) or scenarios.COMMON_LIMITS
    return Explained(
        result={"text": text},
        assumptions=assumptions,
        calculation=calculation[:8],
        sources=scenarios._dedupe(sources),
        limitations=limitations,
        data_quality=DataQuality(
            sufficient=True, missing=[], coverage_days=core_calls.coverage(state, as_of)
        ),
    )
