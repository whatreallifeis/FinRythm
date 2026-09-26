"""Сценарии помощника без LLM (origin/front:docs/ai-scenarios.md).

Каждый сценарий берёт Explained из app.core (через core_calls) и формулирует текст вокруг его чисел.
Здесь ничего не считается: числа только форматируются, assumptions/calculation/limitations/data_quality
переносятся из core как есть. Обращение — на «вы».
"""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.ai import core_calls
from app.ai.amounts import extract_amount
from app.ai.core_calls import CoreNotReady
from app.ai.tools import KnowledgeSearch
from app.core.money import days_word, fmt_rub
from app.models import CalcStep, DataQuality, Explained, SourceRef, UserState

COMMON_LIMITS = [
    "Расчёт сделан по загруженным данным. Банковские счета не подключены.",
    "Это не инвестиционная рекомендация и не операция с деньгами. Решение остаётся за вами.",
]

CATEGORY_LABELS = {
    "food": "Еда",
    "transport": "Транспорт",
    "subscriptions": "Подписки и связь",
    "entertainment": "Развлечения",
    "health": "Здоровье",
    "education": "Образование",
    "rent": "Жильё",
    "other": "Прочее",
}
# Статьи, которые не предлагаем сокращать в первую очередь.
ESSENTIAL_CATEGORIES = {"rent", "transport", "health", "education"}

MONTHS = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]

MISSING_AMOUNT = "сумма покупки — сколько хотите потратить"
MISSING_BALANCE = "текущий баланс"
MISSING_INCOME = "хотя бы одно регулярное поступление: стипендия, зарплата или подработка"
MISSING_PAYMENTS = "обязательные платежи: аренда, связь, проезд, подписки — загрузите выписку, где они есть"
MISSING_OPERATIONS = "операции хотя бы за один месяц — загрузите выписку из банка"
MISSING_TERM = (
    "проверенного источника по этому термину у меня нет — уточните термин, например: "
    "инфляция, вклад, кредитная история, подушка безопасности, ключевая ставка"
)
MISSING_TASK = "уточните задачу: расходы, бюджет до поступления, термин или сумма покупки"
MISSING_CORE = "расчёт для этого вопроса ещё не подключён — попробуйте чуть позже"


# ---------------------------------------------------------------- форматирование


def human_date(value: str | dt.date) -> str:
    d = dt.date.fromisoformat(value) if isinstance(value, str) else value
    return f"{d.day} {MONTHS[d.month - 1]}"


def label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category)


def fmt_pct(share: Any) -> str:
    """Доля 0..1 → «35%»."""
    return f"{(Decimal(str(share)) * 100).quantize(Decimal(1), ROUND_HALF_UP)}%"


def _dedupe(items: list[Any]) -> list[Any]:
    out: list[Any] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


# ---------------------------------------------------------------- сборка Explained


def insufficient(
    missing: list[str], coverage_days: int = 0, limitations: list[str] | None = None
) -> Explained:
    return Explained(
        result={"text": ""},
        limitations=limitations or COMMON_LIMITS,
        data_quality=DataQuality(sufficient=False, missing=_dedupe(missing), coverage_days=coverage_days),
    )


def compose(
    text: str,
    parts: list[Explained],
    *,
    assumptions: list[str] | None = None,
    limitations: list[str] | None = None,
    sources: list[SourceRef] | None = None,
    coverage_days: int | None = None,
) -> Explained:
    """Текст + обёртка объяснимости из результатов core (без пересчёта)."""
    # Шаг с тем же названием и числом из другого расчёта («Текущий баланс») показываем один раз.
    calculation: list[CalcStep] = []
    for step in (step for part in parts for step in part.calculation):
        if all((step.label, step.value) != (seen.label, seen.value) for seen in calculation):
            calculation.append(step)
    all_sources = _dedupe([s for part in parts for s in part.sources] + (sources or []))
    if coverage_days is None:
        coverage_days = max((p.data_quality.coverage_days for p in parts), default=0)
    return Explained(
        result={"text": text},
        assumptions=_dedupe([a for part in parts for a in part.assumptions] + (assumptions or [])),
        calculation=calculation,
        sources=all_sources,
        limitations=_dedupe([lim for part in parts for lim in part.limitations] + (limitations or []))
        or COMMON_LIMITS,
        data_quality=DataQuality(sufficient=True, missing=[], coverage_days=coverage_days),
    )


def _not_sufficient(parts: list[Explained]) -> Explained | None:
    """Если core сказал, что данных не хватает, — передаём это пользователю как есть."""
    bad = [p for p in parts if not p.data_quality.sufficient]
    if not bad:
        return None
    missing = [m for p in bad for m in p.data_quality.missing] or [MISSING_TASK]
    limitations = _dedupe([lim for p in bad for lim in p.limitations])
    return insufficient(missing, max(p.data_quality.coverage_days for p in parts), limitations)


# ---------------------------------------------------------------- impulse


def impulse(question: str, state: UserState, as_of: dt.date) -> Explained:
    amount = extract_amount(question)
    if amount is None:
        return insufficient([MISSING_AMOUNT], core_calls.coverage(state, as_of))
    if state.balance is None:
        return insufficient([MISSING_BALANCE], core_calls.coverage(state, as_of))
    check = core_calls.impulse(state, amount, as_of)
    if bad := _not_sufficient([check]):
        return bad
    return compose(impulse_text(check.result), [check])


def impulse_text(r: dict) -> str:
    amount = fmt_rub(r["amount"])
    before, after = fmt_rub(r["todaySafeSpendBefore"]), fmt_rub(r["todaySafeSpendAfter"])
    wait = r.get("waitUntil")
    if r["verdict"] == "ok":
        text = (
            f"Покупка на {amount} влезает: дневной лимит станет {after} вместо {before}, "
            "обязательные платежи не пострадают."
        )
    elif r["verdict"] == "wait":
        text = f"Покупку на {amount} лучше отложить: сейчас она сократит дневной лимит с {before} до {after}"
        if r.get("redDaysAfter", 0) > r.get("redDaysBefore", 0):
            text += f", а красных дней станет {r['redDaysAfter']} вместо {r['redDaysBefore']}"
        text += "."
        if wait:
            text += (
                f" После поступления «{wait['title']}» {human_date(wait['date'])} "
                f"(через {days_word(wait['daysUntil'])}) покупка уже не сожмёт бюджет."
            )
    else:
        text = (
            f"Сейчас покупка на {amount} не влезает: после обязательных платежей баланс уйдёт в минус — "
            f"до {fmt_rub(r['lowestBalanceAfter'])}."
        )
        if wait:
            text += f" Безопаснее подождать поступления «{wait['title']}» {human_date(wait['date'])}."
        else:
            text += " Покупку лучше отложить."
    if impact := r.get("goalImpact"):
        text += f" Цель «{impact['goalTitle']}» отодвинется примерно на {days_word(impact['delayDays'])}."
    return text


# ---------------------------------------------------------------- budget


def _recurring_payments(state: UserState) -> bool:
    return any(op.is_recurring and op.amount < 0 for op in state.transactions)


def budget(question: str, state: UserState, as_of: dt.date) -> Explained:
    missing = []
    if state.balance is None:
        missing.append(MISSING_BALANCE)
    if not state.incomes:
        missing.append(MISSING_INCOME)
    if not _recurring_payments(state):
        missing.append(MISSING_PAYMENTS)
    if missing:
        return insufficient(missing, core_calls.coverage(state, as_of))

    forecast = core_calls.forecast(state, as_of)
    runway = core_calls.runway(state, as_of)
    goals = [(g, core_calls.goal_plan(state, g.id, as_of)) for g in state.goals if g.deadline]
    if bad := _not_sufficient([forecast, runway]):
        return bad
    goals = [(g, plan) for g, plan in goals if plan is not None and plan.data_quality.sufficient]

    assumptions = []
    if not state.goals:
        assumptions.append("Цель накопления не задана — план составлен без отчислений на цель.")
    elif not goals:
        assumptions.append("У целей нет срока — сколько откладывать в месяц, посчитать не из чего.")
    parts = [forecast, runway] + [plan for _, plan in goals]
    return compose(budget_text(forecast.result, runway.result, goals), parts, assumptions=assumptions)


def budget_text(f: dict, rw: dict, goals: list) -> str:
    text = (
        f"До конца месяца можно тратить около {fmt_rub(f['safeDailySpend'])} в день, "
        f"к последнему числу останется примерно {fmt_rub(f['projectedBalance'])}."
    )
    if f.get("verdict") == "tight":
        text += " Запас небольшой: крупные необязательные покупки лучше отложить."
    elif f.get("verdict") == "shortfall":
        text += " При нынешних обязательных платежах денег до конца месяца не хватает."
    if nxt := rw.get("nextIncome"):
        text += (
            f" До поступления «{nxt['title']}» {days_word(nxt['daysUntil'])}, "
            f"безопасный расход до него — {fmt_rub(rw['todaySafeSpend'])} в день."
        )
    if rw.get("redDays"):
        text += f" Дней с минусом в календаре: {rw['redDays']}."
    for goal, plan in goals:
        p = plan.result
        text += f" На цель «{goal.title}» откладывайте около {fmt_rub(p['monthlyPace'])} в месяц"
        if p.get("etaDate"):
            text += f" — тогда она будет достигнута к {human_date(p['etaDate'])} {p['etaDate'][:4]} года"
        text += "."
    return text


# ---------------------------------------------------------------- expenses


def expenses(question: str, state: UserState, as_of: dt.date) -> Explained:
    if not state.transactions:
        return insufficient([MISSING_OPERATIONS], 0)
    overview = core_calls.overview(state, as_of)
    if bad := _not_sufficient([overview]):
        return bad
    return compose(expenses_text(overview.result), [overview])


def expenses_text(o: dict) -> str:
    cats = o.get("byCategory", [])
    text = (
        f"С {human_date(o['periodFrom'])} по {human_date(o['periodTo'])} расходы — "
        f"{fmt_rub(o['totalExpense'])}, из них регулярные платежи — {fmt_rub(o['recurringTotal'])}."
    )
    if cats:
        top = "; ".join(
            f"{label(c['category'])} — {fmt_rub(c['amount'])} ({fmt_pct(c['share'])})" for c in cats[:3]
        )
        text += f" Больше всего уходит на: {top}."
    if o.get("anomalies"):
        text += " Необычные траты: " + "; ".join(a["reason"] for a in o["anomalies"][:2]) + "."
    optional = [label(c["category"]) for c in cats if c["category"] not in ESSENTIAL_CATEGORIES]
    if optional:
        text += (
            f" Сократить проще всего необязательные статьи — {', '.join(optional[:3]).lower()}; "
            "аренду и проезд лучше не трогать."
        )
    return text


# ---------------------------------------------------------------- glossary


def _fragment(item: Any) -> dict:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    return vars(item)


def glossary(question: str, state: UserState, as_of: dt.date, kb: KnowledgeSearch | None) -> Explained:
    found = [_fragment(r) for r in kb.search(question, k=1)] if kb is not None else []
    if not found:
        return insufficient(
            [MISSING_TERM],
            core_calls.coverage(state, as_of),
            ["Отвечаю только по терминам с проверенным источником и не придумываю определения."],
        )
    item = found[0]
    text = item["text"]
    if item.get("mistake"):
        text += f" Типичная ошибка: {item['mistake']}"
    return compose(
        text,
        [],
        assumptions=["Определение взято из проверенного источника, а не придумано."],
        sources=[SourceRef(title=item.get("source_title") or item["title"], url=item["url"])],
        limitations=["Это объяснение термина, а не совет открывать вклад, брать кредит или инвестировать."],
        coverage_days=core_calls.coverage(state, as_of),
    )


# ---------------------------------------------------------------- free


def looks_like_glossary(question: str) -> bool:
    q = question.casefold()
    return q.startswith("что такое") or any(w in q for w in ("объясни", "что значит", "что означает"))


def looks_like_impulse(question: str) -> bool:
    q = question.casefold()
    return extract_amount(question) is not None and any(
        w in q for w in ("куп", "покуп", "хватит", "потрат", "взять", "можно ли")
    )


def looks_like_expenses(question: str) -> bool:
    q = question.casefold()
    return any(w in q for w in ("расход", "трат", "трач", "куда уход", "категор"))


def looks_like_budget(question: str) -> bool:
    q = question.casefold()
    return any(
        w in q
        for w in (
            "бюджет",
            "накоп",
            "стипенд",
            "до зарплат",
            "хватит ли",
            "до конца месяца",
            "лимит",
            "отлож",
        )
    )


def classify_free(question: str) -> str | None:
    """Ближайший сценарий для свободного вопроса или None."""
    for scenario, check in (
        ("glossary", looks_like_glossary),
        ("impulse", looks_like_impulse),
        ("expenses", looks_like_expenses),
        ("budget", looks_like_budget),
    ):
        if check(question):
            return scenario
    return None


def run(
    scenario_id: str, question: str, state: UserState, as_of: dt.date, kb: KnowledgeSearch | None
) -> Explained:
    if scenario_id == "free":
        scenario_id = classify_free(question) or "clarify"
    try:
        if scenario_id == "impulse":
            return impulse(question, state, as_of)
        if scenario_id == "budget":
            return budget(question, state, as_of)
        if scenario_id == "expenses":
            return expenses(question, state, as_of)
        if scenario_id == "glossary":
            return glossary(question, state, as_of, kb)
    except CoreNotReady:
        return insufficient([MISSING_CORE], core_calls.coverage(state, as_of))
    return insufficient([MISSING_TASK], core_calls.coverage(state, as_of))
