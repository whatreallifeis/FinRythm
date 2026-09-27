"""Полная финансовая сводка пользователя: все числа, которые нужны помощнику и экранам.

Требования ТЗ к результату (Кейс 1, «Требования к результату») — и где они здесь:
  * анализ ситуации: доходы, расходы, регулярные платежи, баланс — `months`, `current`, `regular`;
  * структура расходов: категории с долями и изменением, регулярные и крупные траты — `current`;
  * расчёты кодом: суммы, проценты, остатки, прогноз — `forecast`, `runway`;
  * накопления и цели: темп, срок, влияние расходов — `goals`;
  * финансовый риск: необычные траты и закономерности — `risks`;
  * честность при нехватке данных — `missing`.

Модель (GigaChat) не считает: она получает эту сводку текстом (`report_text`) и объясняет её,
а проверка чисел сверяет каждое число ответа со сводкой (`report_numbers`).
Все деньги — Decimal; в JSON их переводит api.serialize.
"""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Any

from app.core.analysis import ANOMALY_SHARE, _same_period_last_month, build_forecast, build_goal_plan
from app.core.explain import coverage_days, human_date
from app.core.money import fmt_rub, to_money
from app.core.runway_calendar import TIGHT_FLOOR, bills_of, build_runway, next_on_day, normalize_merchant
from app.models import Operation, UserState

ZERO = Decimal(0)
HUNDRED = Decimal(100)
# Необязательные статьи: их помощник может предлагать сокращать. Жильё, проезд, здоровье и учёбу — нет.
DISCRETIONARY = ("food", "entertainment", "subscriptions", "other")
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
MONTHS_NOM = (
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
)
RECURRING_HEAVY_SHARE = Decimal("0.5")  # регулярные платежи съедают больше половины регулярного дохода
TOP_MERCHANTS = 5


def label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category)


def pct(part: Decimal, whole: Decimal) -> Decimal:
    """Доля в процентах с одним знаком: 27,3."""
    if not whole:
        return ZERO
    return (part / whole * HUNDRED).quantize(Decimal("0.1"), ROUND_HALF_UP)


def fmt_pct(value: Decimal) -> str:
    """«11,4%», «−22,1%», «30%»."""
    text = f"{abs(value).normalize():f}".replace(".", ",")
    return f"{'−' if value < 0 else ''}{text}%"


def fmt_delta(value: int) -> str:
    """«+53%», «−11%»."""
    return f"{'+' if value > 0 else '−' if value < 0 else ''}{abs(value)}%"


def month_key(day: dt.date) -> str:
    return f"{day.year}-{day.month:02d}"


def month_title(key: str) -> str:
    year, month = key.split("-")
    return f"{MONTHS_NOM[int(month) - 1]} {year}"


def _spent(ops: list[Operation]) -> Decimal:
    return -sum((op.amount for op in ops if op.amount < 0), ZERO)


def _earned(ops: list[Operation]) -> Decimal:
    return sum((op.amount for op in ops if op.amount > 0), ZERO)


# ---------------------------------------------------------------- месяцы


def _months(ops: list[Operation], as_of: dt.date) -> list[dict]:
    by_month: dict[str, list[Operation]] = {}
    for op in ops:
        by_month.setdefault(month_key(op.date), []).append(op)
    out = []
    for key in sorted(by_month):
        rows = by_month[key]
        income, expense = _earned(rows), _spent(rows)
        recurring = _spent([op for op in rows if op.is_recurring])
        out.append(
            {
                "month": key,
                "title": month_title(key),
                "complete": key != month_key(as_of),
                "income": to_money(income),
                "expense": to_money(expense),
                "net": to_money(income - expense),
                # Доля дохода, которая осталась (норма сбережений); отрицательная — потратили больше.
                "savingsRatePct": pct(income - expense, income) if income else None,
                "recurringExpense": to_money(recurring),
                "oneOffExpense": to_money(expense - recurring),
                "operations": len(rows),
            }
        )
    return out


# ---------------------------------------------------------------- текущий месяц


def _top_merchants(rows: list[Operation], limit: int) -> list[dict]:
    """Куда ушло больше всего денег среди расходов: описание, сумма, число операций."""
    merchants: dict[str, dict] = {}
    for op in rows:
        if op.amount >= 0:
            continue
        item = merchants.setdefault(
            normalize_merchant(op.merchant), {"merchant": op.merchant, "amount": ZERO, "count": 0}
        )
        item["amount"] += -op.amount
        item["count"] += 1
    top = sorted(merchants.values(), key=lambda m: -m["amount"])[:limit]
    return [{**m, "amount": to_money(m["amount"])} for m in top]


def _current(ops: list[Operation], as_of: dt.date) -> dict:
    start = as_of.replace(day=1)
    rows = [op for op in ops if start <= op.date <= as_of]
    prev_start, prev_end = _same_period_last_month(as_of)
    prev_rows = [op for op in ops if prev_start <= op.date <= prev_end]

    expense = _spent(rows)
    income = _earned(rows)
    recurring = _spent([op for op in rows if op.is_recurring])
    one_off = expense - recurring

    categories = []
    for category in sorted({op.category for op in rows if op.amount < 0}):
        cat_rows = [op for op in rows if op.amount < 0 and op.category == category]
        amount = _spent(cat_rows)
        prev = _spent([op for op in prev_rows if op.category == category])
        categories.append(
            {
                "category": category,
                "label": label(category),
                "amount": to_money(amount),
                "sharePct": pct(amount, expense),
                "count": len(cat_rows),
                "prevAmount": to_money(prev),
                "deltaPct": int(pct(amount - prev, prev).to_integral_value(ROUND_HALF_UP)) if prev else None,
                "discretionary": category in DISCRETIONARY,
                "topMerchants": _top_merchants(cat_rows, 2),
            }
        )
    categories.sort(key=lambda c: -c["amount"])

    top = _top_merchants([op for op in rows if not op.is_recurring], TOP_MERCHANTS)

    large = [
        {
            "date": op.date.isoformat(),
            "merchant": op.merchant,
            "amount": to_money(-op.amount),
            "sharePct": pct(-op.amount, expense),
        }
        for op in rows
        if op.amount < 0 and not op.is_recurring and expense and -op.amount > expense * ANOMALY_SHARE
    ]

    return {
        "month": month_key(as_of),
        "title": month_title(month_key(as_of)),
        "from": start.isoformat(),
        "to": as_of.isoformat(),
        "daysPassed": as_of.day,
        "income": to_money(income),
        "expense": to_money(expense),
        "net": to_money(income - expense),
        "prevPeriod": f"{prev_start.isoformat()} — {prev_end.isoformat()}",
        "prevExpense": to_money(_spent(prev_rows)),
        "expenseDeltaPct": (
            int(pct(expense - _spent(prev_rows), _spent(prev_rows)).to_integral_value(ROUND_HALF_UP))
            if _spent(prev_rows)
            else None
        ),
        "recurringExpense": to_money(recurring),
        "recurringSharePct": pct(recurring, expense),
        "oneOffExpense": to_money(one_off),
        "avgDailyOneOff": to_money(one_off / as_of.day),
        "discretionaryExpense": to_money(sum((c["amount"] for c in categories if c["discretionary"]), ZERO)),
        "categories": categories,
        "topMerchants": top,
        "large": large,
    }


# ---------------------------------------------------------------- регулярное


def _regular(state: UserState, ops: list[Operation], as_of: dt.date) -> dict:
    payments = [
        {
            "title": bill.title,
            "amount": to_money(bill.amount),
            "day": bill.day,
            "nextDate": next_on_day(as_of, bill.day).isoformat(),
            "category": bill.category,
            "label": label(bill.category),
            "source": bill.source,
            "annual": to_money(bill.amount * 12),
        }
        for bill in sorted(bills_of(state), key=lambda b: (b.day, b.title))
    ]
    incomes = [
        {
            "title": inc.title,
            "amount": to_money(inc.amount),
            "day": inc.day_of_month,
            "nextDate": next_on_day(as_of, inc.day_of_month).isoformat(),
        }
        for inc in sorted(state.incomes, key=lambda i: i.day_of_month)
    ]
    monthly_bills = sum((p["amount"] for p in payments), ZERO)
    monthly_income = sum((i["amount"] for i in incomes), ZERO)
    regular_titles = {normalize_merchant(inc.title) for inc in state.incomes}

    # Нерегулярные поступления — за последний полный месяц (подработка, переводы через СБП).
    prev_month = month_key(as_of.replace(day=1) - dt.timedelta(days=1))
    irregular = sum(
        (
            op.amount
            for op in ops
            if op.amount > 0
            and month_key(op.date) == prev_month
            and normalize_merchant(op.merchant) not in regular_titles
        ),
        ZERO,
    )
    subscriptions = [p for p in payments if p["category"] == "subscriptions"]
    return {
        "payments": payments,
        "monthlyPayments": to_money(monthly_bills),
        "annualPayments": to_money(monthly_bills * 12),
        "subscriptionsMonthly": to_money(sum((p["amount"] for p in subscriptions), ZERO)),
        "incomes": incomes,
        "monthlyIncome": to_money(monthly_income),
        "paymentsShareOfIncomePct": pct(monthly_bills, monthly_income) if monthly_income else None,
        "freeAfterPayments": to_money(monthly_income - monthly_bills),
        "irregularIncomeLastMonth": to_money(irregular),
        "irregularIncomeMonth": month_title(prev_month),
    }


# ---------------------------------------------------------------- цели


def _free_monthly(months: list[dict]) -> Decimal | None:
    """Сколько реально остаётся за месяц: доходы минус расходы последнего полного месяца."""
    complete = [m for m in months if m["complete"]]
    return complete[-1]["net"] if complete else None


def _goal_verdict(deadline: dt.date | None, required: Decimal | None, free: Decimal | None) -> str:
    """Готовый вывод по цели — модели не нужно сравнивать числа самой."""
    if free is None:
        return "нет полного месяца операций — темп накопления не посчитать"
    if free <= 0:
        return "сейчас на цель ничего не остаётся: за прошлый месяц расходы были больше доходов"
    if deadline is None:
        return "срок не задан — можно назвать только, за сколько месяцев цель наберётся при нынешнем темпе"
    if required is None:
        return "срок уже прошёл или цель собрана"
    if free >= required:
        return "к сроку успеваете: остаётся больше, чем нужно откладывать"
    return "к сроку не успеваете: остаётся меньше, чем нужно откладывать"


def _goals(state: UserState, as_of: dt.date, free: Decimal | None, current: dict) -> list[dict]:
    out = []
    cut = sum(
        (c["amount"] / 2 for c in current["categories"] if c["discretionary"] and c["category"] != "other"),
        ZERO,
    )
    for goal in state.goals:
        remaining = max(goal.target_amount - goal.saved_amount, ZERO)
        plan = build_goal_plan(state, goal.id, as_of)
        required = plan.result.get("monthlyPace") if plan and plan.data_quality.sufficient else None
        eta_now = (remaining / free).to_integral_value(rounding=ROUND_CEILING) if free and free > 0 else None
        eta_cut = (
            (remaining / (free + cut)).to_integral_value(rounding=ROUND_CEILING)
            if free is not None and free + cut > 0 and cut > 0
            else None
        )
        out.append(
            {
                "title": goal.title,
                "target": to_money(goal.target_amount),
                "saved": to_money(goal.saved_amount),
                "remaining": to_money(remaining),
                "progressPct": pct(goal.saved_amount, goal.target_amount),
                "deadline": goal.deadline.isoformat() if goal.deadline else None,
                "monthsToDeadline": (goal.deadline - as_of).days // 30 if goal.deadline else None,
                "requiredMonthly": required,
                "freeMonthly": free,
                "etaMonthsAtCurrentPace": int(eta_now) if eta_now is not None else None,
                "onTrack": bool(required is not None and free is not None and free >= required),
                "verdict": _goal_verdict(goal.deadline, required, free),
                # Если урезать необязательные траты этого месяца вдвое — на цель добавится столько.
                "extraIfCutHalf": to_money(cut),
                "etaMonthsIfCutHalf": int(eta_cut) if eta_cut is not None else None,
            }
        )
    return out


# ---------------------------------------------------------------- риски


def _risks(report: dict, state: UserState) -> list[dict]:
    risks = []
    runway = report["runway"]
    if runway and runway["redDays"]:
        first = runway["firstShortfallDate"]
        risks.append(
            {
                "kind": "cash_gap",
                "severity": "critical",
                "text": f"Кассовый разрыв: {human_date(dt.date.fromisoformat(first))} баланс уйдёт в минус, "
                f"минимальный остаток {fmt_rub(runway['lowestBalance'])}, "
                f"дней в минусе: {runway['redDays']}.",
            }
        )
    elif runway and runway["lowestBalance"] < TIGHT_FLOOR:
        risks.append(
            {
                "kind": "tight",
                "severity": "warning",
                "text": f"Впритык: до поступления остаток опустится до {fmt_rub(runway['lowestBalance'])}.",
            }
        )
    complete = [m for m in report["months"] if m["complete"]]
    if complete and complete[-1]["net"] < 0:
        last = complete[-1]
        risks.append(
            {
                "kind": "overspending",
                "severity": "warning",
                "text": f"За {last['title']} расходы превысили доходы на {fmt_rub(-last['net'])}.",
            }
        )
    for item in report["current"]["large"]:
        risks.append(
            {
                "kind": "large_purchase",
                "severity": "info",
                "text": f"Крупная разовая трата: {item['merchant']} {fmt_rub(item['amount'])} — "
                f"{fmt_pct(item['sharePct'])} расходов месяца.",
            }
        )
    regular = report["regular"]
    share = regular["paymentsShareOfIncomePct"]
    if share is not None and share > RECURRING_HEAVY_SHARE * HUNDRED:
        risks.append(
            {
                "kind": "heavy_payments",
                "severity": "warning",
                "text": (
                    f"Регулярные платежи ({fmt_rub(regular['monthlyPayments'])} в месяц) больше регулярного "
                    f"дохода ({fmt_rub(regular['monthlyIncome'])}) — их приходится покрывать "
                    "нерегулярными поступлениями."
                    if share > HUNDRED
                    else f"Регулярные платежи забирают {fmt_pct(share)} регулярного дохода."
                ),
            }
        )
    if regular["subscriptionsMonthly"]:
        risks.append(
            {
                "kind": "subscriptions",
                "severity": "info",
                "text": f"Подписки и связь: {fmt_rub(regular['subscriptionsMonthly'])} в месяц, "
                f"{fmt_rub(regular['subscriptionsMonthly'] * 12)} в год.",
            }
        )
    if state.balance is not None and state.balance < TIGHT_FLOOR:
        risks.append(
            {
                "kind": "low_balance",
                "severity": "warning",
                "text": f"На счёте всего {fmt_rub(state.balance)}.",
            }
        )
    return risks


# ---------------------------------------------------------------- сводка


def build_report(state: UserState, as_of: dt.date) -> dict[str, Any]:
    """Все посчитанные числа по данным пользователя на дату as_of."""
    ops = [op for op in state.transactions if op.date <= as_of]
    missing = []
    if not ops:
        missing.append("операции хотя бы за один месяц")
    if state.balance is None:
        missing.append("текущий баланс")
    if not state.incomes:
        missing.append("регулярное поступление с датой: стипендия, зарплата или перевод")

    months = _months(ops, as_of)
    current = _current(ops, as_of)

    runway = None
    runway_ex = build_runway(state, as_of)
    if runway_ex.data_quality.sufficient:
        r = runway_ex.result
        shortfall = next((d["date"] for d in r["days"] if d["status"] == "shortfall"), None)
        runway = {
            "nextIncome": r["nextIncome"],
            "todaySafeSpend": r["todaySafeSpend"],
            "lowestBalance": r["lowestBalance"],
            "redDays": r["redDays"],
            "horizonTo": r["horizonTo"],
            "firstShortfallDate": shortfall,
            "paymentsBeforeIncome": [
                {"date": d["date"], "title": e["title"], "amount": -e["amount"]}
                for d in r["days"]
                for e in d["events"]
                if e["amount"] < 0 and (r["nextIncome"] is None or d["date"] < r["nextIncome"]["date"])
            ],
        }
    forecast_ex = build_forecast(state, as_of)
    forecast = forecast_ex.result if forecast_ex.data_quality.sufficient else None

    report: dict[str, Any] = {
        "asOf": as_of.isoformat(),
        "period": {
            "from": min(op.date for op in ops).isoformat() if ops else None,
            "to": as_of.isoformat(),
            "coverageDays": coverage_days(state.transactions, as_of),
            "operations": len(ops),
        },
        "balance": to_money(state.balance) if state.balance is not None else None,
        "months": months,
        "current": current,
        "regular": _regular(state, ops, as_of),
        "runway": runway,
        "forecast": forecast,
        "missing": missing,
    }
    report["goals"] = _goals(state, as_of, _free_monthly(months), current)
    report["risks"] = _risks(report, state)
    return report


# ---------------------------------------------------------------- текст для модели


def _money_or_dash(value: Any) -> str:
    return "нет данных" if value is None else fmt_rub(value)


def report_text(report: dict[str, Any]) -> str:
    """Сводка короткими строками по-русски — контекст для модели. Числа — в том же виде, что в ответах."""
    lines = [f"Дата расчёта: {human_date(dt.date.fromisoformat(report['asOf']))}."]
    period = report["period"]
    if period["from"]:
        lines.append(
            f"Выписка: с {human_date(dt.date.fromisoformat(period['from']))} по "
            f"{human_date(dt.date.fromisoformat(period['to']))}, операций: {period['operations']}."
        )
    lines.append(f"Баланс сейчас: {_money_or_dash(report['balance'])}.")

    lines.append("По месяцам:")
    for m in report["months"]:
        rate = "" if m["savingsRatePct"] is None else f", осталось {fmt_pct(m['savingsRatePct'])} дохода"
        state = "" if m["complete"] else " (месяц ещё идёт)"
        lines.append(
            f"- {m['title']}{state}: доходы {fmt_rub(m['income'])}, расходы {fmt_rub(m['expense'])}, "
            f"итог {fmt_rub(m['net'])}{rate}; регулярные {fmt_rub(m['recurringExpense'])}, "
            f"разовые {fmt_rub(m['oneOffExpense'])}."
        )

    c = report["current"]
    delta = (
        ""
        if c["expenseDeltaPct"] is None
        else f" ({fmt_delta(c['expenseDeltaPct'])} к тому же периоду прошлого месяца)"
    )
    lines.append(
        f"Текущий месяц ({c['title']}, {c['daysPassed']} дн.): расходы {fmt_rub(c['expense'])}{delta}, "
        f"из них регулярные {fmt_rub(c['recurringExpense'])} ({fmt_pct(c['recurringSharePct'])}), "
        f"разовые {fmt_rub(c['oneOffExpense'])}, в среднем разовых {fmt_rub(c['avgDailyOneOff'])} в день."
    )
    lines.append("Категории текущего месяца:")
    for cat in c["categories"]:
        change = "" if cat["deltaPct"] is None else f", {fmt_delta(cat['deltaPct'])} к прошлому месяцу"
        where = ", ".join(f"{m['merchant']} {fmt_rub(m['amount'])}" for m in cat["topMerchants"])
        lines.append(
            f"- {cat['label']}: {fmt_rub(cat['amount'])}, {fmt_pct(cat['sharePct'])} расходов, "
            f"операций {cat['count']}{change}; больше всего — {where}"
            + ("." if cat["discretionary"] else "; обязательная статья, её не сокращаем.")
        )
    if c["topMerchants"]:
        lines.append(
            "Куда больше всего разовых трат: "
            + "; ".join(
                f"{m['merchant']} — {fmt_rub(m['amount'])} ({m['count']} шт.)" for m in c["topMerchants"]
            )
            + "."
        )

    r = report["regular"]
    if r["incomes"]:
        lines.append(
            "Регулярные поступления: "
            + "; ".join(
                f"{i['title']} {fmt_rub(i['amount'])} {i['day']}-го, следующее "
                f"{human_date(dt.date.fromisoformat(i['nextDate']))}"
                for i in r["incomes"]
            )
            + f". Всего {fmt_rub(r['monthlyIncome'])} в месяц."
        )
    else:
        lines.append("Регулярных поступлений в данных нет.")
    if r["irregularIncomeLastMonth"]:
        lines.append(
            f"Нерегулярные поступления за {r['irregularIncomeMonth']}: "
            f"{fmt_rub(r['irregularIncomeLastMonth'])}."
        )
    if r["payments"]:
        lines.append(
            "Регулярные платежи: "
            + "; ".join(
                f"{p['title']} {fmt_rub(p['amount'])} {p['day']}-го ({p['label']})" for p in r["payments"]
            )
            + f". Всего {fmt_rub(r['monthlyPayments'])} в месяц, {fmt_rub(r['annualPayments'])} в год."
        )
        if r["paymentsShareOfIncomePct"] is not None:
            lines.append(
                f"Регулярные платежи — {fmt_pct(r['paymentsShareOfIncomePct'])} регулярного дохода; "
                f"после них остаётся {fmt_rub(r['freeAfterPayments'])} в месяц."
            )

    rw = report["runway"]
    if rw:
        nxt = rw["nextIncome"]
        if nxt:
            lines.append(
                f"До следующего поступления («{nxt['title']}» {fmt_rub(nxt['amount'])}, "
                f"{human_date(dt.date.fromisoformat(nxt['date']))}) {nxt['daysUntil']} дн.; "
                f"можно тратить {fmt_rub(rw['todaySafeSpend'])} в день."
            )
        if rw["paymentsBeforeIncome"]:
            lines.append(
                "Платежи до поступления: "
                + "; ".join(
                    f"{p['title']} {fmt_rub(p['amount'])} {human_date(dt.date.fromisoformat(p['date']))}"
                    for p in rw["paymentsBeforeIncome"]
                )
                + "."
            )
        lines.append(
            f"Минимальный остаток по календарю: {fmt_rub(rw['lowestBalance'])}; "
            f"дней в минусе: {rw['redDays']}."
        )
    f = report["forecast"]
    if f:
        lines.append(
            f"До конца месяца {f['daysLeft']} дн.: ожидается поступлений {fmt_rub(f['expectedIncome'])}, "
            f"платежей {fmt_rub(f['plannedExpenses'])}, "
            f"остаток к концу месяца {fmt_rub(f['projectedBalance'])}, "
            f"можно тратить {fmt_rub(f['safeDailySpend'])} в день."
        )

    for g in report["goals"]:
        parts = [
            f"Цель «{g['title']}»: {fmt_rub(g['target'])}, накоплено {fmt_rub(g['saved'])} "
            f"({fmt_pct(g['progressPct'])}), осталось {fmt_rub(g['remaining'])}"
        ]
        if g["deadline"]:
            parts.append(f"срок {human_date(dt.date.fromisoformat(g['deadline']))} {g['deadline'][:4]} года")
        else:
            parts.append("срок не задан")
        if g["requiredMonthly"] is not None:
            parts.append(f"чтобы успеть, откладывать {fmt_rub(g['requiredMonthly'])} в месяц")
        if g["freeMonthly"] is not None:
            parts.append(f"за прошлый месяц после всех расходов осталось {fmt_rub(g['freeMonthly'])}")
        if g["monthsToDeadline"] is not None:
            parts.append(f"до срока {g['monthsToDeadline']} мес.")
        if g["etaMonthsAtCurrentPace"] is not None:
            parts.append(f"при таком темпе — {g['etaMonthsAtCurrentPace']} мес.")
        if g["etaMonthsIfCutHalf"] is not None:
            parts.append(
                f"если урезать необязательные траты вдвое (+{fmt_rub(g['extraIfCutHalf'])} в месяц) — "
                f"{g['etaMonthsIfCutHalf']} мес."
            )
        parts.append(f"вывод: {g['verdict']}")
        lines.append("; ".join(parts).rstrip(".") + ".")

    if report["risks"]:
        lines.append("Риски:")
        lines += [f"- {risk['text']}" for risk in report["risks"]]
    if report["missing"]:
        lines.append("Не хватает данных: " + "; ".join(report["missing"]) + ".")
    return "\n".join(lines)
