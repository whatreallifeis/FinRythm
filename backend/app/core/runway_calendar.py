"""Календарь до следующего поступления и проверка покупки (calendar.py ветки front).

Лимит на день и проверка покупки считаются одним календарём, иначе их числа разойдутся.
Отличия от ветки front (issue #12): без поступлений платёж в последний день горизонта тоже резервируется.
"""

from __future__ import annotations

import calendar
import datetime as dt
import hashlib
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from app.core.explain import coverage_days, explained, human_date, step
from app.core.money import days_word, floor_rub, fmt_rub, to_money
from app.models import Explained, Operation, SavingGoal, UserState

ZERO = Decimal(0)
TIGHT_FLOOR = Decimal("2000")  # ниже этого остатка день «впритык»
DEFAULT_HORIZON_DAYS = 14  # горизонт, если нет ни платежей, ни поступлений
PURCHASE_TITLE = "Покупка"


@dataclass(frozen=True)
class Event:
    date: dt.date
    title: str
    amount: Decimal  # < 0 — платёж, > 0 — поступление


@dataclass(frozen=True)
class Day:
    date: dt.date
    events: tuple[Event, ...]
    balance: Decimal
    status: str


@dataclass(frozen=True)
class Plan:
    """Календарь пользователя на дату as_of: события, горизонт и дата, до которой считается лимит."""

    as_of: dt.date
    balance: Decimal
    events: list[Event]
    horizon_end: dt.date
    next_income: Event | None

    @property
    def until(self) -> dt.date:
        return self.next_income.date if self.next_income else self.horizon_end


def normalize_merchant(merchant: str) -> str:
    return " ".join(merchant.casefold().replace("ё", "е").split())


def next_on_day(as_of: dt.date, day_of_month: int) -> dt.date:
    """Ближайшая дата строго после as_of с этим днём месяца; 31-е в коротком месяце — последний день."""
    year, month = as_of.year, as_of.month
    candidate = _clamp(year, month, day_of_month)
    if candidate <= as_of:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        candidate = _clamp(year, month, day_of_month)
    return candidate


def _clamp(year: int, month: int, day: int) -> dt.date:
    return dt.date(year, month, min(day, calendar.monthrange(year, month)[1]))


def recurring_bills(transactions: list[Operation]) -> list[tuple[str, Decimal, int]]:
    """Регулярный расход становится будущим платежом в тот же день месяца (по последней операции)."""
    latest: dict[str, Operation] = {}
    for op in transactions:
        if not op.is_recurring or op.amount >= 0:
            continue
        key = normalize_merchant(op.merchant)
        if key not in latest or op.date >= latest[key].date:
            latest[key] = op
    return [(op.merchant, -op.amount, op.date.day) for op in latest.values()]


@dataclass(frozen=True)
class Bill:
    """Платёж календаря: регулярный расход из выписки или автоплатёж, добавленный вручную."""

    id: str
    title: str
    amount: Decimal  # > 0
    day: int
    category: str
    source: str  # "detected" — по операциям, "manual" — добавлен пользователем


def bill_id(merchant: str) -> str:
    """Стабильный id регулярного расхода из выписки: по нормализованному описанию."""
    return "rec-" + hashlib.sha1(normalize_merchant(merchant).encode()).hexdigest()[:10]


def bills_of(state: UserState) -> list[Bill]:
    """Все платежи календаря. Ручной автоплатёж с тем же названием, что и регулярный расход
    из выписки, не дублируется: сумма и день берутся из последней операции."""
    latest: dict[str, Operation] = {}
    for op in state.transactions:
        if not op.is_recurring or op.amount >= 0:
            continue
        key = normalize_merchant(op.merchant)
        if key not in latest or op.date >= latest[key].date:
            latest[key] = op
    bills = [
        Bill(bill_id(op.merchant), op.merchant, -op.amount, op.date.day, op.category, "detected")
        for op in latest.values()
    ]
    bills += [
        Bill(rule.id, rule.title, rule.amount, rule.day_of_month, rule.category, "manual")
        for rule in state.autopayments
        if normalize_merchant(rule.title) not in latest
    ]
    return bills


def planned_events(state: UserState, as_of: dt.date) -> list[Event]:
    events = [Event(next_on_day(as_of, bill.day), bill.title, -bill.amount) for bill in bills_of(state)]
    events += [Event(next_on_day(as_of, inc.day_of_month), inc.title, inc.amount) for inc in state.incomes]
    events.sort(key=lambda e: (e.date, e.title))
    return events


def make_plan(state: UserState, as_of: dt.date) -> Plan:
    events = planned_events(state, as_of)
    horizon_end = events[-1].date if events else as_of + dt.timedelta(days=DEFAULT_HORIZON_DAYS)
    next_income = next((e for e in events if e.amount > 0 and e.date > as_of), None)
    return Plan(as_of, state.balance or ZERO, events, horizon_end, next_income)


def _status(balance: Decimal) -> str:
    if balance < 0:
        return "shortfall"
    if balance < TIGHT_FLOOR:
        return "tight"
    return "ok"


def simulate_days(plan: Plan, purchase: tuple[Decimal, dt.date] | None = None) -> list[Day]:
    """Остаток на конец каждого дня от as_of до горизонта; покупка — (сумма, дата)."""
    cursor = plan.balance
    days: list[Day] = []
    current = plan.as_of
    while current <= plan.horizon_end:
        todays = [e for e in plan.events if e.date == current]
        if purchase and purchase[1] == current and purchase[0] > 0:
            todays.append(Event(current, PURCHASE_TITLE, -purchase[0]))
        cursor += sum((e.amount for e in todays), ZERO)
        days.append(Day(current, tuple(todays), cursor, _status(cursor)))
        current += dt.timedelta(days=1)
    return days


def bills_until(plan: Plan) -> list[Event]:
    """Платежи, которые надо оплатить из текущего баланса: после сегодня и до поступления.

    Платёж в день поступления оплачивается из него. Если поступлений нет, резервируется и платёж
    в последний день горизонта (в ветке front он терялся, issue #12).
    """
    if plan.next_income is None:
        return [e for e in plan.events if e.amount < 0 and plan.as_of < e.date <= plan.until]
    return [e for e in plan.events if e.amount < 0 and plan.as_of < e.date < plan.until]


def safe_daily(plan: Plan, balance: Decimal) -> Decimal:
    days = max((plan.until - plan.as_of).days, 1)
    free = balance + sum((e.amount for e in bills_until(plan)), ZERO)
    return floor_rub(free / days) if free > 0 else ZERO


def _summary(days: list[Day]) -> tuple[int, Decimal]:
    if not days:
        return 0, ZERO
    return sum(1 for d in days if d.status == "shortfall"), min(d.balance for d in days)


def _public_income(event: Event | None, as_of: dt.date) -> dict | None:
    if event is None:
        return None
    return {
        "date": event.date.isoformat(),
        "title": event.title,
        "amount": to_money(event.amount),
        "daysUntil": (event.date - as_of).days,
    }


def _public_days(days: list[Day]) -> list[dict]:
    return [
        {
            "date": d.date.isoformat(),
            "events": [{"title": e.title, "amount": to_money(e.amount)} for e in d.events],
            "balance": to_money(d.balance),
            "status": d.status,
        }
        for d in days
    ]


def _coverage(state: UserState, as_of: dt.date) -> int:
    return coverage_days(state.transactions, as_of)


def _income_today_note(state: UserState, as_of: dt.date) -> list[str]:
    today = [inc.title for inc in state.incomes if _clamp(as_of.year, as_of.month, inc.day_of_month) == as_of]
    if not today:
        return []
    names = ", ".join(f"«{t}»" for t in today)
    return [f"Поступление {names} сегодня считаем уже зачисленным в баланс; следующее — через месяц."]


def _no_income_note(plan: Plan) -> list[str]:
    """Без поступлений горизонт условный — говорим об этом прямо, а не выдаём лимит за факт."""
    if plan.next_income is not None:
        return []
    return [
        f"Поступлений в профиле нет — лимит посчитан так, будто до {human_date(plan.horizon_end)} "
        "денег больше не придёт. Добавьте стипендию или зарплату с днём месяца, чтобы расчёт был точнее."
    ]


# ---------------------------------------------------------------- runway


def _empty_runway(as_of: dt.date) -> dict:
    return {
        "horizonTo": as_of.isoformat(),
        "nextIncome": None,
        "todaySafeSpend": ZERO,
        "lowestBalance": ZERO,
        "redDays": 0,
        "days": [],
    }


def build_runway(state: UserState, as_of: dt.date) -> Explained:
    """Календарь дней до последнего известного события со статусами ok / tight / shortfall."""
    missing = []
    if state.balance is None:
        missing.append("текущий баланс")
    if not state.incomes:
        missing.append("хотя бы одно регулярное поступление с днём месяца")
    if missing:
        return explained(_empty_runway(as_of), coverage=_coverage(state, as_of), missing=missing)

    plan = make_plan(state, as_of)
    days = simulate_days(plan)
    red, lowest = _summary(days)
    safe = safe_daily(plan, plan.balance)
    bills = bills_until(plan)
    bills_sum = -sum((e.amount for e in bills), ZERO)
    nxt = plan.next_income
    n_days = max((plan.until - as_of).days, 1)
    result = {
        "horizonTo": plan.horizon_end.isoformat(),
        "nextIncome": _public_income(nxt, as_of),
        "todaySafeSpend": safe,
        "lowestBalance": to_money(lowest),
        "redDays": red,
        "days": _public_days(days),
    }
    return explained(
        result,
        coverage=_coverage(state, as_of),
        assumptions=[
            "Календарь идёт от сегодня до последнего известного платежа или поступления.",
            "Обязательные платежи стоят в те же дни месяца, что и регулярные операции.",
            *_income_today_note(state, as_of),
        ],
        calculation=[
            step("Текущий баланс", "остаток на счёте", plan.balance),
            step(
                "Дней до поступления",
                f"до «{nxt.title}» {human_date(nxt.date)}" if nxt else "нет ближайшего дохода",
                (nxt.date - as_of).days if nxt else 0,
            ),
            step(
                "Обязательные платежи до поступления",
                ", ".join(f"{e.title} {fmt_rub(-e.amount)}" for e in bills) or "нет",
                bills_sum,
            ),
            step(
                "Можно тратить в день",
                f"({fmt_rub(plan.balance)} − {fmt_rub(bills_sum)}) / {days_word(n_days)}",
                safe,
            ),
            step("Минимальный остаток", "после всех обязательных платежей на горизонте", to_money(lowest)),
        ],
    )


# ---------------------------------------------------------------- impulse


def _empty_impulse(amount: Decimal) -> dict:
    return {
        "amount": to_money(amount),
        "verdict": "wait",
        "hint": "Укажите текущий баланс — без него покупку не проверить.",
        "todaySafeSpendBefore": ZERO,
        "todaySafeSpendAfter": ZERO,
        "redDaysBefore": 0,
        "redDaysAfter": 0,
        "lowestBalanceAfter": ZERO,
        "waitUntil": None,
        "goalImpact": None,
        "daysAfter": [],
    }


def _goal_impact(goals: list[SavingGoal], as_of: dt.date, amount: Decimal) -> dict | None:
    """На сколько дней покупка отодвинет первую цель со сроком при темпе «успеть к сроку»."""
    goal = next((g for g in goals if g.deadline and g.saved_amount < g.target_amount), None)
    if goal is None or goal.deadline is None:
        return None
    days_left = (goal.deadline - as_of).days
    if days_left <= 0:
        return None
    daily = (goal.target_amount - goal.saved_amount) / Decimal(days_left)
    delay = int((amount / daily).to_integral_value(rounding=ROUND_CEILING))
    return {"goalTitle": goal.title, "delayDays": max(delay, 1)}


def _wait_until(plan: Plan, amount: Decimal) -> Event | None:
    """Первое поступление, после которого покупка не уводит ни один день в минус."""
    for event in plan.events:
        if event.amount <= 0 or event.date <= plan.as_of:
            continue
        red, low = _summary(simulate_days(plan, (amount, event.date)))
        if low >= 0 and red == 0:
            return event
    return None


def _hint(verdict: str, spend_after: Decimal, low_after: Decimal, wait: Event | None) -> str:
    if verdict == "ok":
        return (
            f"Покупка влезает: дневной лимит станет {fmt_rub(spend_after)}, "
            "обязательные платежи не пострадают."
        )
    if wait:
        when = human_date(wait.date)
        if verdict == "wait":
            return f"Лучше подождать до «{wait.title}» {when}: тогда покупка не сожмёт дни до поступления."
        return (
            "Сейчас не влезет: после обязательных платежей баланс уйдёт в минус. "
            f"Подождите «{wait.title}» {when}."
        )
    if verdict == "wait":
        return f"Покупка влезает впритык: остаток опустится до {fmt_rub(low_after)}. Лучше отложить."
    return "Сейчас не влезет: после обязательных платежей не хватит денег. Покупку лучше отложить."


def check_impulse(state: UserState, amount: Decimal, as_of: dt.date) -> Explained:
    """Что будет с календарём, если потратить amount сегодня: verdict ok / wait / shortfall."""
    amount = Decimal(amount)
    if amount <= 0:
        raise ValueError("Сумма покупки должна быть больше нуля")
    if state.balance is None:
        return explained(_empty_impulse(amount), coverage=_coverage(state, as_of), missing=["текущий баланс"])

    plan = make_plan(state, as_of)
    red_before, low_before = _summary(simulate_days(plan))
    after = simulate_days(plan, (amount, as_of))
    red_after, low_after = _summary(after)
    spend_before = safe_daily(plan, plan.balance)
    spend_after = safe_daily(plan, plan.balance - amount)

    verdict = "ok"
    if low_after < 0:
        verdict = "shortfall"
    elif red_after > red_before or low_after < TIGHT_FLOOR <= low_before:
        verdict = "wait"
    wait = _wait_until(plan, amount) if verdict != "ok" else None

    result = {
        "amount": to_money(amount),
        "verdict": verdict,
        "hint": _hint(verdict, spend_after, low_after, wait),
        "todaySafeSpendBefore": spend_before,
        "todaySafeSpendAfter": spend_after,
        "redDaysBefore": red_before,
        "redDaysAfter": red_after,
        "lowestBalanceAfter": to_money(low_after),
        "waitUntil": _public_income(wait, as_of),
        "goalImpact": _goal_impact(state.goals, as_of, amount),
        "daysAfter": _public_days(after),
    }
    return explained(
        result,
        coverage=_coverage(state, as_of),
        assumptions=[
            "Покупка списывается сегодня, обязательные платежи остаются на своих датах.",
            "Поступления берутся из профиля.",
            *_income_today_note(state, as_of),
            *_no_income_note(plan),
        ],
        calculation=[
            step("Покупка", "сумма, которую хотите потратить сегодня", to_money(amount)),
            step("Лимит в день до покупки", "свободные деньги / дни до поступления", spend_before),
            step(
                "Лимит в день после покупки",
                f"то же после списания {fmt_rub(amount)}",
                spend_after,
            ),
            step("Минимальный остаток после покупки", "худший день на горизонте", to_money(low_after)),
        ],
    )
