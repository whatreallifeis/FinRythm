"""Один день календаря на главной (GET /api/calendar/{date}): операции дня и справка по регулярным.

Прошедший день — операции из выписки. Будущий — план: регулярные платежи (из выписки и ручные
автоплатежи) и поступления, которые приходятся на это число. Остаток на конец дня — из того же
календаря, что лимит «можно тратить в день», поэтому числа на экране не расходятся.

Справка («note») собирается шаблоном вокруг чисел; если подключена модель, API отдаёт её
на переписывание живым языком с проверкой чисел (app.ai.day_note).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.core.explain import coverage_days, explained, human_date, step
from app.core.money import fmt_rub, to_money
from app.core.runway_calendar import _clamp, bills_of, build_runway, normalize_merchant
from app.models import Explained, UserState

ZERO = Decimal(0)
MIN_SAME_WEEKDAYS = 2  # меньше двух таких же дней недели — «обычно» не посчитать


def occurs_on(day_of_month: int, day: dt.date) -> bool:
    """Платёж на 31-е в коротком месяце приходится на последний день месяца."""
    return _clamp(day.year, day.month, day_of_month) == day


def _operations(state: UserState, day: dt.date, as_of: dt.date) -> list[dict]:
    actual = [
        {
            "ref": {"kind": "transaction", "id": op.id},
            "title": op.merchant,
            "amount": to_money(op.amount),
            "category": op.category,
            "isRecurring": op.is_recurring,
        }
        for op in state.transactions
        if op.date == day
    ]
    if day <= as_of:
        return actual
    incomes = [
        {
            "ref": {"kind": "income", "id": inc.id},
            "title": inc.title,
            "amount": to_money(inc.amount),
            "category": "other",
            "isRecurring": True,
        }
        for inc in state.incomes
        if occurs_on(inc.day_of_month, day)
    ]
    bills = [
        {
            "ref": {"kind": "autopayment", "id": bill.id},
            "title": bill.title,
            "amount": to_money(-bill.amount),
            "category": bill.category,
            "isRecurring": True,
        }
        for bill in bills_of(state)
        if occurs_on(bill.day, day)
    ]
    return incomes + bills


def _typical(state: UserState, day: dt.date, as_of: dt.date) -> tuple[Decimal, Decimal, int] | None:
    """Средние разовые траты в тот же день недели за всю историю до сегодня: (среднее, всего, дней)."""
    dates = [op.date for op in state.transactions if op.date < as_of]
    if not dates:
        return None
    first = min(dates)
    same = sum(
        1 for n in range((as_of - first).days) if (first + dt.timedelta(days=n)).weekday() == day.weekday()
    )
    if same < MIN_SAME_WEEKDAYS:
        return None
    spent = -sum(
        (
            op.amount
            for op in state.transactions
            if op.amount < 0
            and not op.is_recurring
            and op.date < as_of
            and op.date.weekday() == day.weekday()
        ),
        ZERO,
    )
    average = (spent / same / 10).quantize(Decimal(1)) * 10
    return average, to_money(spent), same


def _expense_note(state: UserState, op: dict, day: dt.date, as_of: dt.date, monthly: Decimal) -> str:
    amount = -op["amount"]
    key = normalize_merchant(op["title"])
    history = sorted(
        (
            t
            for t in state.transactions
            if t.is_recurring and t.amount < 0 and normalize_merchant(t.merchant) == key and t.date < day
        ),
        key=lambda t: t.date,
    )
    if not history:
        first = (
            f"{op['title']} — {fmt_rub(amount)}, регулярный платёж. Это первое его списание в выписке."
            if day <= as_of
            else f"{op['title']} — {fmt_rub(amount)}, регулярный платёж {day.day}-го числа. "
            "В выписке его истории пока нет, дата взята из графика платежей."
        )
        parts = [first]
    else:
        last = -history[-1].amount
        if last == amount:
            trend = f"сумма не менялась с {human_date(history[0].date)}"
        elif amount > last:
            trend = f"сумма выросла с {fmt_rub(last)} до {fmt_rub(amount)}"
        else:
            trend = f"сумма снизилась с {fmt_rub(last)} до {fmt_rub(amount)}"
        parts = [f"{op['title']} — {fmt_rub(amount)}, списывается каждый месяц; {trend}."]

    share = int((amount / monthly * 100).quantize(Decimal(1))) if monthly else 0
    largest = all(bill.amount <= amount for bill in bills_of(state))
    if largest and share:
        parts.append(f"Это самый крупный обязательный платёж — {share}% всех регулярных расходов месяца.")
    elif op["category"] == "subscriptions":
        parts.append(
            f"Если платить весь год, выйдет {fmt_rub(amount * 12)} — "
            "стоит проверить, пользуетесь ли вы этим сервисом."
        )
    elif share >= 5:
        parts.append(f"Это {share}% регулярных расходов месяца.")
    return " ".join(parts)


def _income_note(op: dict, day: dt.date) -> str:
    return (
        f"{op['title']} — {fmt_rub(op['amount'])}, регулярное поступление {day.day}-го числа. "
        "С этого дня сумма, которую можно тратить в день, пересчитывается до следующих денег."
    )


def build_day_insight(state: UserState, day: dt.date, as_of: dt.date) -> Explained:
    kind = "past" if day < as_of else "today" if day == as_of else "future"
    operations = _operations(state, day, as_of)
    typical = _typical(state, day, as_of)

    balance = status = None
    if day >= as_of:
        runway = build_runway(state, as_of)
        if runway.data_quality.sufficient:
            match = next((d for d in runway.result["days"] if d["date"] == day.isoformat()), None)
            if match:
                balance, status = match["balance"], match["status"]

    recurring = [op for op in operations if op["isRecurring"]]
    monthly = sum((bill.amount for bill in bills_of(state)), ZERO)
    note = None
    if recurring:
        lines = [
            _income_note(op, day) if op["amount"] > 0 else _expense_note(state, op, day, as_of, monthly)
            for op in recurring
        ]
        outflow = sum((op["amount"] for op in recurring if op["amount"] < 0), ZERO)
        if balance is not None and outflow < 0:
            if status == "shortfall":
                lines.append(
                    f"После списаний баланс уйдёт в минус: {fmt_rub(-balance)} не хватит. "
                    "Отложите разовые покупки до ближайшего поступления."
                )
            elif status == "tight":
                lines.append(
                    f"После списаний останется {fmt_rub(balance)} — это впритык. "
                    "Крупные покупки лучше не планировать на эти дни."
                )
            else:
                lines.append(
                    f"После списаний останется около {fmt_rub(balance)} — платежи проходят без напряжения."
                )
        note = "\n\n".join(lines)

    calculation = []
    if recurring:
        calculation.append(
            step(
                "Регулярные операции дня",
                " + ".join(f"{op['title']} {fmt_rub(op['amount'])}" for op in recurring),
                sum((op["amount"] for op in recurring), ZERO),
            )
        )
    if typical:
        average, spent, same = typical
        calculation.append(
            step("Обычные траты в этот день недели", f"{fmt_rub(spent)} разовых трат / {same} дн.", average)
        )
    if balance is not None:
        calculation.append(step("Остаток на конец дня", "прогноз по календарю до поступления", balance))

    missing = [] if state.transactions or state.incomes else ["загруженные операции — хотя бы за пару недель"]
    return explained(
        {
            "date": day.isoformat(),
            "kind": kind,
            "operations": operations,
            "typicalSpend": typical[0] if typical else None,
            "balance": balance,
            "status": status,
            "note": note,
        },
        coverage=coverage_days(state.transactions, as_of),
        assumptions=(
            [
                "В план дня входят регулярные платежи и поступления в те же числа месяца, что раньше.",
                "Разовые покупки в план не входят — их проверяет «Могу купить это сегодня?».",
            ]
            if kind == "future"
            else [
                "Операции взяты из загруженной выписки.",
                "Регулярным считается платёж, который повторяется каждый месяц примерно в одно число.",
            ]
        ),
        calculation=calculation,
        missing=missing,
    )
