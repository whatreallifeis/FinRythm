"""Дневной лимит и «что если» по docs/01_project_spec.md §6.1 (эталон — contracts/reference_runway.py)."""

from __future__ import annotations

import calendar
import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from app.core.money import CENT, days_word, floor_rub, fmt_num, fmt_rub, to_money
from app.models import (
    Assumption,
    MandatoryPayment,
    MissingData,
    PaymentOccurrence,
    Profile,
    RunwayResult,
    SimulationResult,
)

ZERO = Decimal(0)


def _as_of(profile: Profile, today: dt.date | None) -> dt.date:
    return today or profile.as_of or dt.date.today()


def _add_months(d: dt.date, months: int) -> dt.date:
    m = d.month - 1 + months
    year, month = d.year + m // 12, m % 12 + 1
    return d.replace(year=year, month=month, day=min(d.day, calendar.monthrange(year, month)[1]))


def payment_occurrences(p: MandatoryPayment, start: dt.date, end: dt.date) -> list[PaymentOccurrence]:
    """Все повторения платежа с датой в полуинтервале [start, end)."""
    out: list[PaymentOccurrence] = []
    n, d = 0, p.next_date
    while d < end:
        if d >= start:
            out.append(PaymentOccurrence(title=p.title, amount=p.amount, date=d))
        if p.period == "once":
            break
        n += 1
        d = _add_months(p.next_date, n) if p.period == "monthly" else p.next_date + dt.timedelta(weeks=n)
    return out


def _formula(
    *,
    balance: Decimal,
    purchase: Decimal,
    mandatory: Decimal,
    reserve: Decimal,
    goal: Decimal,
    counted: Decimal,
    available: Decimal,
    horizon: int,
    limit: Decimal,
) -> str:
    terms = [fmt_num(balance)]
    if purchase > 0:
        terms.append(f"− {fmt_num(purchase)} покупка")
    if mandatory > 0:
        terms.append(f"− {fmt_num(mandatory)} обяз.")
    if reserve > 0:
        terms.append(f"− {fmt_num(reserve)} резерв")
    if goal > 0:
        terms.append(f"− {fmt_num(goal)} в цель")
    if counted > 0:
        terms.append(f"+ {fmt_num(counted)} ожид.")
    expr = " ".join(terms)
    if available < 0:
        return f"{expr} = {fmt_rub(available)}: не хватает {fmt_rub(-available)} до поступления"
    if len(terms) > 1:
        expr = f"({expr})"
    return f"{expr} ÷ {horizon} дн. = {fmt_rub(limit)} в день"


def calculate_runway(
    profile: Profile,
    *,
    purchase: Decimal = Decimal(0),
    delay_days: int = 0,
    k: Decimal | None = None,
    today: dt.date | None = None,
) -> RunwayResult:
    as_of = _as_of(profile, today)
    purchase = Decimal(purchase)
    s = profile.settings
    k = s.expected_income_k if k is None else Decimal(k)

    if profile.balance is None:
        return RunwayResult(
            status="insufficient_data",
            as_of=as_of,
            missing=[
                MissingData(field="balance", message="Укажите текущий баланс — без него лимит не посчитать")
            ],
        )

    assumptions: list[Assumption] = []

    def assume(code: str, text: str) -> None:
        assumptions.append(Assumption(code=code, text=text))

    confirmed = sorted((i for i in profile.incomes if i.confirmed and i.date >= as_of), key=lambda i: i.date)
    if confirmed:
        income = confirmed[0]
        next_date = income.date + dt.timedelta(days=delay_days)
        next_title: str | None = income.title
        horizon = max(1, (next_date - as_of).days)
        assumed = False
        if (next_date - as_of).days <= 0:
            assume("income_today", "Поступление сегодня — считаем на 1 день")
    else:
        horizon = s.default_horizon_days + delay_days
        next_date = as_of + dt.timedelta(days=horizon)
        next_title = None
        assumed = True
        assume(
            "horizon_default",
            f"Дата следующего поступления не указана — считаем на {days_word(s.default_horizon_days)}",
        )
    end = as_of + dt.timedelta(days=horizon)

    items = sorted(
        (o for p in profile.payments for o in payment_occurrences(p, as_of, end)),
        key=lambda o: o.date,
    )
    mandatory = sum((o.amount for o in items), ZERO)
    if not profile.payments:
        assume("no_payments", "Обязательные платежи не указаны — если они есть, лимит завышен")

    free = profile.balance - purchase - mandatory
    reserve = (max(ZERO, free) * s.reserve_pct / 100).quantize(CENT, ROUND_HALF_UP)
    per_day = sum((g.daily_contribution for g in profile.goals), ZERO)
    planned_goal = per_day * horizon
    goal = min(planned_goal, max(ZERO, free - reserve))

    expected = sum(
        (i.amount for i in profile.incomes if not i.confirmed and as_of <= i.date < end),
        ZERO,
    )
    counted = (k * expected).quantize(CENT, ROUND_HALF_UP)
    available = free - reserve - goal + counted

    if available < 0:
        status, limit, deficit = "deficit", ZERO, -available
    else:
        status, limit, deficit = "ok", floor_rub(available / horizon), ZERO

    if expected > 0:
        if counted > 0:
            assume(
                "expected_income_counted",
                f"Учтено {fmt_num(k * 100)}% ожидаемых поступлений ({fmt_rub(expected)}) "
                "— эти деньги ещё не пришли",
            )
        else:
            assume(
                "expected_income_ignored",
                f"Ожидаемые поступления ({fmt_rub(expected)}) не учтены, пока не придут",
            )
    if goal < planned_goal:
        assume("goal_paused", "Взнос в цель уменьшен/приостановлен: не хватает денег до поступления")
    if reserve > 0:
        assume("reserve", f"Отложен резерв {fmt_num(s.reserve_pct)}% на непредвиденное")
    if delay_days > 0:
        assume("delay", f"Сценарий: поступление задерживается на {days_word(delay_days)}")
    if purchase > 0:
        assume("purchase", f"Сценарий: покупка на {fmt_rub(purchase)}")

    return RunwayResult(
        status=status,
        as_of=as_of,
        next_income_date=next_date,
        next_income_title=next_title,
        horizon_days=horizon,
        horizon_is_assumed=assumed,
        balance=to_money(profile.balance),
        mandatory_total=to_money(mandatory),
        mandatory_items=items,
        free=to_money(free),
        reserve=reserve,
        goal_contribution=to_money(goal),
        expected_income_counted=counted,
        available=to_money(available),
        daily_limit=limit,
        deficit=to_money(deficit),
        formula_text=_formula(
            balance=profile.balance,
            purchase=purchase,
            mandatory=mandatory,
            reserve=reserve,
            goal=goal,
            counted=counted,
            available=available,
            horizon=horizon,
            limit=limit,
        ),
        assumptions=assumptions,
    )


def simulate(
    profile: Profile,
    *,
    purchase: Decimal = Decimal(0),
    delay_days: int = 0,
    today: dt.date | None = None,
) -> SimulationResult:
    before = calculate_runway(profile, today=today)
    after = calculate_runway(profile, purchase=purchase, delay_days=delay_days, today=today)
    return SimulationResult(
        purchase=Decimal(purchase),
        delay_days=delay_days,
        before=before,
        after=after,
        delta_daily_limit=after.daily_limit - before.daily_limit,
    )
