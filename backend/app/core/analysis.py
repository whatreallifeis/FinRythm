"""Обзор расходов, прогноз до конца месяца и план цели (analysis.py ветки front).

Отличия от ветки front (issue #12):
  * прогноз не разрешает тратить деньги на платежи сразу после конца месяца и не даёт лимит
    больше, чем календарь до поступления;
  * регулярные операции (аренда) не попадают в «разовые траты»;
  * deltaPercent сравнивает с тем же отрезком прошлого месяца, а не со всем месяцем;
  * цель, которая уже накоплена, не требует срока.
"""

from __future__ import annotations

import calendar
import datetime as dt
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from app.core.explain import coverage_days, explained, human_date, step
from app.core.money import ceil_rub, days_word, floor_rub, fmt_num, fmt_rub, to_money
from app.core.runway_calendar import (
    ZERO,
    bills_until,
    make_plan,
    next_on_day,
    recurring_bills,
    safe_daily,
)
from app.models import CATEGORY_IDS, Explained, Operation, UserState

ANOMALY_SHARE = Decimal("0.25")  # трата больше 25% расходов месяца
SHARE_STEP = Decimal("0.0001")
DISCRETIONARY = {"food", "entertainment", "subscriptions", "other"}
CATEGORY_HINTS = {
    "food": "Еда вне дома — заметная часть необязательных расходов",
    "entertainment": "Крупная трата на развлечения отодвигает цель",
    "subscriptions": "Подписки списываются каждый месяц, даже если ими не пользуются",
    "other": "В «другом» часто прячутся разовые покупки",
}


def month_end(day: dt.date) -> dt.date:
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def _same_period_last_month(as_of: dt.date) -> tuple[dt.date, dt.date]:
    """Тот же отрезок прошлого месяца: 1–26 августа для 26 сентября; последний день → весь месяц."""
    prev_end_of_month = as_of.replace(day=1) - dt.timedelta(days=1)
    start = prev_end_of_month.replace(day=1)
    if as_of == month_end(as_of):
        return start, prev_end_of_month
    return start, prev_end_of_month.replace(day=min(as_of.day, prev_end_of_month.day))


def _expenses_by_category(ops: list[Operation]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for op in ops:
        if op.amount < 0:
            totals[op.category] = totals.get(op.category, ZERO) - op.amount
    return totals


def _in(op: Operation, start: dt.date, end: dt.date) -> bool:
    return start <= op.date <= end


# ---------------------------------------------------------------- overview


def _empty_overview(as_of: dt.date) -> dict:
    return {
        "periodFrom": as_of.replace(day=1).isoformat(),
        "periodTo": as_of.isoformat(),
        "totalIncome": ZERO,
        "totalExpense": ZERO,
        "recurringTotal": ZERO,
        "byCategory": [],
        "anomalies": [],
    }


def build_overview(state: UserState, as_of: dt.date) -> Explained:
    """Расходы и доходы с 1-го числа по as_of: доли категорий 0..1, изменение к прошлому месяцу, аномалии."""
    coverage = coverage_days(state.transactions, as_of)
    if not state.transactions:
        return explained(_empty_overview(as_of), coverage=0, missing=["операции хотя бы за один месяц"])
    start = as_of.replace(day=1)
    current = [op for op in state.transactions if _in(op, start, as_of)]
    if not current:
        return explained(_empty_overview(as_of), coverage=coverage, missing=["операции за текущий месяц"])

    prev_start, prev_end = _same_period_last_month(as_of)
    prev_by = _expenses_by_category([op for op in state.transactions if _in(op, prev_start, prev_end)])
    expenses = [op for op in current if op.amount < 0]
    total_expense = -sum((op.amount for op in expenses), ZERO)
    total_income = sum((op.amount for op in current if op.amount > 0), ZERO)
    recurring = -sum((op.amount for op in expenses if op.is_recurring), ZERO)

    slices = []
    for category, amount in _expenses_by_category(current).items():
        prev = prev_by.get(category)
        delta = None
        if prev:
            delta = int(((amount - prev) / prev * 100).quantize(Decimal(1), ROUND_HALF_UP))
        share = (amount / total_expense).quantize(SHARE_STEP, ROUND_HALF_UP) if total_expense else ZERO
        slices.append(
            {
                "category": category,
                "amount": to_money(amount),
                "share": min(share, Decimal(1)),
                "deltaPercent": delta,
            }
        )
    slices.sort(key=lambda s: (-s["amount"], CATEGORY_IDS.index(s["category"])))

    anomalies = []
    for op in expenses:
        spent = -op.amount
        if total_expense and not op.is_recurring and spent > total_expense * ANOMALY_SHARE:
            percent = int((spent / total_expense * 100).quantize(Decimal(1), ROUND_HALF_UP))
            anomalies.append(
                {
                    "transactionId": op.id,
                    "reason": f"Разовая трата {fmt_rub(spent)} — это {percent}% расходов месяца",
                }
            )

    share_pct = (
        int((recurring / total_expense * 100).quantize(Decimal(1), ROUND_HALF_UP)) if total_expense else 0
    )
    result = {
        "periodFrom": start.isoformat(),
        "periodTo": as_of.isoformat(),
        "totalIncome": to_money(total_income),
        "totalExpense": to_money(total_expense),
        "recurringTotal": to_money(recurring),
        "byCategory": slices,
        "anomalies": anomalies,
    }
    return explained(
        result,
        coverage=coverage,
        assumptions=[
            f"Период: {start.isoformat()} — {as_of.isoformat()}.",
            "Регулярные — аренда, подписки, проезд и повтор из месяца в месяц.",
            f"Изменение по категориям — к тому же отрезку прошлого месяца: "
            f"{prev_start.day}–{human_date(prev_end)}.",
            "Разовая трата — нерегулярная операция больше 25% расходов месяца.",
        ],
        calculation=[
            step("Расходы за период", "сумма операций со знаком минус", to_money(total_expense)),
            step("из них регулярные", "операции с признаком «регулярный»", to_money(recurring)),
            step(
                "Доля регулярных, %",
                f"{fmt_rub(recurring)} / {fmt_rub(total_expense)} × 100",
                share_pct,
            ),
        ],
    )


# ---------------------------------------------------------------- forecast


def _days_left(as_of: dt.date) -> int:
    return max((month_end(as_of) - as_of).days, 1)


def _empty_forecast(as_of: dt.date) -> dict:
    return {
        "daysLeft": _days_left(as_of),
        "expectedIncome": ZERO,
        "plannedExpenses": ZERO,
        "projectedBalance": ZERO,
        "safeDailySpend": ZERO,
        "verdict": "shortfall",
    }


def build_forecast(state: UserState, as_of: dt.date) -> Explained:
    """Остаток к концу месяца и сколько можно тратить в день, не трогая деньги на ближайшие платежи."""
    coverage = coverage_days(state.transactions, as_of)
    if state.balance is None:
        return explained(_empty_forecast(as_of), coverage=coverage, missing=["текущий баланс"])

    end = month_end(as_of)
    days_left = _days_left(as_of)
    incomes = [
        (inc.title, inc.amount)
        for inc in state.incomes
        if as_of < next_on_day(as_of, inc.day_of_month) <= end
    ]
    bills = [
        (title, amount)
        for title, amount, day in recurring_bills(state.transactions)
        if as_of < next_on_day(as_of, day) <= end
    ]
    expected = sum((a for _, a in incomes), ZERO)
    planned = sum((a for _, a in bills), ZERO)
    projected = state.balance + expected - planned

    # Платежи после конца месяца, которые придётся оплатить до следующего поступления (issue #12).
    after_plan = make_plan(state, end)
    reserve_bills = bills_until(after_plan)
    reserve = -sum((e.amount for e in reserve_bills), ZERO)
    free = projected - reserve
    month_safe = floor_rub(free / days_left) if free > 0 else ZERO

    # Лимит не больше календарного до ближайшего поступления, иначе числа на экране разойдутся.
    calendar_safe = safe_daily(make_plan(state, as_of), state.balance) if state.incomes else None
    safe = month_safe if calendar_safe is None else min(month_safe, calendar_safe)

    month_start = as_of.replace(day=1)
    spent = -sum(
        (op.amount for op in state.transactions if _in(op, month_start, as_of) and op.amount < 0), ZERO
    )
    average = floor_rub(spent / as_of.day) if spent > 0 else ZERO
    if projected < 0 or free < 0:
        verdict = "shortfall"
    elif average > 0 and safe < average:
        verdict = "tight"
    else:
        verdict = "ok"

    result = {
        "daysLeft": days_left,
        "expectedIncome": to_money(expected),
        "plannedExpenses": to_money(planned),
        "projectedBalance": to_money(projected),
        "safeDailySpend": safe,
        "verdict": verdict,
    }

    def listing(items: list[tuple[str, Decimal]]) -> str:
        return ", ".join(f"{title} {fmt_rub(amount)}" for title, amount in items)

    assumptions = ["Обязательные платежи берутся только из регулярных операций, даты не выдумываются."]
    assumptions.append(
        f"До конца месяца запланировано: {listing(bills)}."
        if bills
        else "До конца месяца в регулярных операциях новых списаний нет."
    )
    assumptions.append(
        f"Ещё ожидается: {listing(incomes)}."
        if incomes
        else "Новых поступлений до конца месяца в профиле нет."
    )
    reserve_list = [(e.title, -e.amount) for e in reserve_bills]
    if reserve_list:
        nxt = after_plan.next_income
        until = f"до «{nxt.title}» {human_date(nxt.date)}" if nxt else "в начале следующего месяца"
        assumptions.append(f"Отложены деньги на платежи после конца месяца {until}: {listing(reserve_list)}.")
    if average:
        assumptions.append(f"В этом месяце вы тратите в среднем {fmt_rub(average)} в день.")

    calculation = [
        step("Текущий баланс", "остаток, который вы указали", state.balance),
        step("Ожидаемые поступления", listing(incomes) or "нет", to_money(expected)),
        step("Обязательные платежи", listing(bills) or "нет", to_money(planned)),
        step("Остаток к концу месяца", "баланс + поступления − обязательные", to_money(projected)),
    ]
    if reserve:
        calculation.append(step("Отложить на платежи после месяца", listing(reserve_list), to_money(reserve)))
    calculation.append(
        step(
            "Можно тратить до конца месяца",
            f"({fmt_rub(projected)} − {fmt_rub(reserve)}) / {days_word(days_left)}"
            if reserve
            else f"{fmt_rub(projected)} / {days_word(days_left)}",
            month_safe,
        )
    )
    if calendar_safe is not None and calendar_safe < month_safe:
        calculation.append(
            step(
                "Лимит календаря до поступления",
                "меньшее из двух — чтобы хватило до поступления",
                calendar_safe,
            )
        )
    return explained(result, coverage=coverage, assumptions=assumptions, calculation=calculation)


# ---------------------------------------------------------------- goal plan


def _goal_result(goal_id: str, **fields: object) -> dict:
    return {
        "goalId": goal_id,
        "monthlyPace": ZERO,
        "etaMonths": None,
        "etaDate": None,
        "blockers": [],
        **fields,
    }


def _blockers(state: UserState, as_of: dt.date, pace: Decimal) -> list[dict]:
    """Две крупнейшие необязательные категории текущего месяца."""
    current = [op for op in state.transactions if _in(op, as_of.replace(day=1), as_of)]
    totals = {c: a for c, a in _expenses_by_category(current).items() if c in DISCRETIONARY}
    ranked = sorted(totals.items(), key=lambda item: (-item[1], CATEGORY_IDS.index(item[0])))[:2]
    blockers = []
    for category, amount in ranked:
        months = int((amount / pace).quantize(Decimal(1), ROUND_HALF_UP)) if pace > 0 else 0
        hint = CATEGORY_HINTS[category]
        if months > 0:
            hint = f"{hint}. За месяц это около {months} мес. отчислений"
        blockers.append({"category": category, "amount": to_money(amount), "hint": hint})
    return blockers


def build_goal_plan(state: UserState, goal_id: str, as_of: dt.date) -> Explained | None:
    """Сколько откладывать в месяц, чтобы успеть к сроку. None — такой цели нет."""
    goal = next((g for g in state.goals if g.id == goal_id), None)
    if goal is None:
        return None
    coverage = coverage_days(state.transactions, as_of)
    remaining = goal.target_amount - goal.saved_amount

    if remaining <= 0:
        return explained(
            _goal_result(goal.id, etaMonths=0, etaDate=as_of.isoformat()),
            coverage=coverage,
            assumptions=["Цель уже накоплена — откладывать на неё больше не нужно."],
            calculation=[
                step("Осталось накопить", "сумма цели − уже отложено", ZERO),
                step("Нужно в месяц", "уже накоплено не меньше суммы цели", ZERO),
            ],
        )
    no_date_limit = ["Без срока нельзя честно назвать дату, когда цель будет достигнута."]
    if goal.deadline is None:
        return explained(
            _goal_result(goal.id),
            coverage=coverage,
            limitations=no_date_limit,
            missing=["срок, к которому нужна сумма"],
        )
    if goal.deadline <= as_of:
        return explained(
            _goal_result(goal.id),
            coverage=coverage,
            limitations=no_date_limit,
            missing=["срок в будущем: указанный срок уже наступил"],
        )

    days_left = (goal.deadline - as_of).days
    months = Decimal(days_left) / Decimal(30)
    pace = ceil_rub(remaining / months)
    eta_months = int((remaining / pace).to_integral_value(rounding=ROUND_CEILING))
    result = _goal_result(
        goal.id,
        monthlyPace=pace,
        etaMonths=eta_months,
        etaDate=goal.deadline.isoformat(),
        blockers=_blockers(state, as_of, pace),
    )
    return explained(
        result,
        coverage=coverage,
        assumptions=["Темп — сколько откладывать в месяц, чтобы успеть к сроку. Это не обещание."],
        calculation=[
            step("Осталось накопить", "сумма цели − уже отложено", to_money(remaining)),
            step(
                "Нужно в месяц",
                f"{fmt_rub(remaining)} / {fmt_num(months)} мес. ({days_word(days_left)} до срока ÷ 30), "
                "с округлением вверх",
                pace,
            ),
        ],
    )
