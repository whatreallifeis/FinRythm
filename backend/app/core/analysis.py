"""Обзор расходов, прогноз до конца месяца и план цели. Все суммы считает этот модуль."""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.core.calendar import next_on_day, recurring_bills
from app.money import D, ceil_ruble, floor_ruble, fmt_rub, rub

CATEGORIES = (
    "food",
    "transport",
    "subscriptions",
    "entertainment",
    "health",
    "education",
    "rent",
    "other",
)

DISCRETIONARY = {"food", "entertainment", "subscriptions", "other"}

CATEGORY_HINTS = {
    "food": "Еда вне дома — заметная часть необязательных расходов",
    "entertainment": "Крупная трата на развлечения отодвигает цель",
    "subscriptions": "Подписки списываются каждый месяц, даже если ими не пользуются",
    "other": "В «другом» часто прячутся разовые покупки",
    "transport": "Проезд повторяется и его стоит заложить в обязательные",
    "health": "Здоровье лучше не резать первым — посмотрите, нет ли разовой крупной траты",
    "education": "Учёба важна; проверьте, это разовый курс или постоянный платёж",
    "rent": "Аренда обязательна, на ней план не ускорить",
}


def month_bounds(day: date) -> tuple[date, date]:
    start = date(day.year, day.month, 1)
    if day.month == 12:
        end = date(day.year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(day.year, day.month + 1, 1) - timedelta(days=1)
    return start, end


def previous_month(day: date) -> str:
    start, _ = month_bounds(day)
    prev = start - timedelta(days=1)
    return prev.strftime("%Y-%m")


def coverage_days(transactions: list[dict], as_of: date) -> int:
    dates = [
        date.fromisoformat(row["date"]) for row in transactions if date.fromisoformat(row["date"]) <= as_of
    ]
    if not dates:
        return 0
    return (as_of - min(dates)).days + 1


def _in_month(row: dict, month: str, until: date | None = None) -> bool:
    when = date.fromisoformat(row["date"])
    if when.strftime("%Y-%m") != month:
        return False
    return until is None or when <= until


def build_overview(transactions: list[dict], as_of: date) -> dict:
    month = as_of.strftime("%Y-%m")
    start, _ = month_bounds(as_of)
    current = [row for row in transactions if _in_month(row, month, as_of)]
    previous = [row for row in transactions if _in_month(row, previous_month(as_of))]
    expenses = [row for row in current if D(row["amount"]) < 0]
    incomes = [row for row in current if D(row["amount"]) > 0]
    total_expense = sum((-D(row["amount"]) for row in expenses), D(0))
    total_income = sum((D(row["amount"]) for row in incomes), D(0))
    recurring = sum((-D(row["amount"]) for row in expenses if row.get("isRecurring")), D(0))

    prev_by: dict[str, Decimal] = {}
    for row in previous:
        amount = D(row["amount"])
        if amount < 0:
            prev_by[row["category"]] = prev_by.get(row["category"], D(0)) + (-amount)

    by_category: dict[str, Decimal] = {}
    for row in expenses:
        by_category[row["category"]] = by_category.get(row["category"], D(0)) + (-D(row["amount"]))

    slices = []
    for category, amount in by_category.items():
        prev = prev_by.get(category)
        delta = None
        if prev and prev > 0:
            delta = int(((amount - prev) / prev * 100).quantize(Decimal("1"), ROUND_HALF_UP))
        share = (
            D(0)
            if total_expense == 0
            else (amount / total_expense).quantize(Decimal("0.0001"), ROUND_HALF_UP)
        )
        slices.append(
            {
                "category": category if category in CATEGORIES else "other",
                "amount": rub(amount),
                "share": float(min(share, D(1))),
                "deltaPercent": delta,
            }
        )
    slices.sort(key=lambda item: item["amount"], reverse=True)

    anomalies = []
    if total_expense > 0:
        for row in expenses:
            spent = -D(row["amount"])
            if spent > total_expense * Decimal("0.25"):
                percent = int((spent / total_expense * 100).quantize(Decimal("1"), ROUND_HALF_UP))
                anomalies.append(
                    {
                        "transactionId": row["id"],
                        "reason": (f"Разовая трата {fmt_rub(spent)} — это {percent}% расходов месяца"),
                    }
                )

    return {
        "periodFrom": start.isoformat(),
        "periodTo": as_of.isoformat(),
        "totalIncome": rub(total_income),
        "totalExpense": rub(total_expense),
        "recurringTotal": rub(recurring),
        "byCategory": slices,
        "anomalies": anomalies,
        "_total_expense": total_expense,
        "_recurring": recurring,
        "_has_rows": bool(current),
    }


def build_forecast(
    balance: Decimal | None, incomes: list[dict], transactions: list[dict], as_of: date
) -> dict:
    _, month_end = month_bounds(as_of)
    days_left = max((month_end - as_of).days, 1)
    expected = D(0)
    expected_titles: list[str] = []
    for income in incomes:
        when = next_on_day(as_of, int(income["dayOfMonth"]))
        if as_of < when <= month_end:
            expected += D(income["amount"])
            expected_titles.append(f"{income['title']} {fmt_rub(D(income['amount']))}")

    planned = D(0)
    planned_titles: list[str] = []
    for title, amount, day in recurring_bills(transactions):
        when = next_on_day(as_of, day)
        if as_of < when <= month_end:
            planned += amount
            planned_titles.append(f"{title} {fmt_rub(amount)}")

    current_balance = balance if balance is not None else D(0)
    projected = current_balance + expected - planned
    safe = floor_ruble(projected / days_left) if projected > 0 else D(0)

    month = as_of.strftime("%Y-%m")
    spent = sum(
        (-D(row["amount"]) for row in transactions if _in_month(row, month, as_of) and D(row["amount"]) < 0),
        D(0),
    )
    elapsed = max(as_of.day, 1)
    average = floor_ruble(spent / elapsed) if spent > 0 else D(0)
    if projected < 0:
        verdict = "shortfall"
    elif average > 0 and safe < average:
        verdict = "tight"
    else:
        verdict = "ok"

    return {
        "daysLeft": days_left,
        "expectedIncome": rub(expected),
        "plannedExpenses": rub(planned),
        "projectedBalance": rub(projected),
        "safeDailySpend": float(safe),
        "verdict": verdict,
        "_expected_titles": expected_titles,
        "_planned_titles": planned_titles,
        "_average": average,
        "_safe": safe,
        "_projected": projected,
        "_balance": current_balance,
    }


def build_goal_plan(goal: dict, transactions: list[dict], as_of: date) -> dict:
    target = D(goal["targetAmount"])
    saved = D(goal["savedAmount"])
    remaining = target - saved
    deadline_raw = goal.get("deadline")
    empty = {
        "goalId": goal["id"],
        "monthlyPace": 0,
        "etaMonths": None,
        "etaDate": None,
        "blockers": [],
    }
    if not deadline_raw:
        return {**empty, "_missing": ["срок, к которому нужна сумма"], "_pace": None, "_remaining": remaining}
    deadline = date.fromisoformat(deadline_raw)
    if deadline <= as_of:
        return {
            **empty,
            "_missing": ["срок в будущем: текущая дата уже позже дедлайна"],
            "_pace": None,
            "_remaining": remaining,
        }
    if remaining <= 0:
        return {
            "goalId": goal["id"],
            "monthlyPace": 0,
            "etaMonths": 0,
            "etaDate": as_of.isoformat(),
            "blockers": [],
            "_missing": [],
            "_pace": D(0),
            "_remaining": D(0),
            "_months": D(0),
            "_done": True,
        }

    days_left = (deadline - as_of).days
    months = Decimal(days_left) / Decimal(30)
    pace = ceil_ruble(remaining / months)
    eta_months = int((remaining / pace).to_integral_value(rounding="ROUND_CEILING"))
    return {
        "goalId": goal["id"],
        "monthlyPace": float(pace),
        "etaMonths": eta_months,
        "etaDate": deadline.isoformat(),
        "blockers": _blockers(transactions, as_of, pace),
        "_missing": [],
        "_pace": pace,
        "_remaining": remaining,
        "_months": months,
        "_days_left": days_left,
        "_done": False,
    }


def _blockers(transactions: list[dict], as_of: date, pace: Decimal) -> list[dict]:
    month = as_of.strftime("%Y-%m")
    totals: dict[str, Decimal] = {}
    for row in transactions:
        if not _in_month(row, month, as_of):
            continue
        amount = D(row["amount"])
        if amount >= 0 or row["category"] not in DISCRETIONARY:
            continue
        totals[row["category"]] = totals.get(row["category"], D(0)) + (-amount)
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:2]
    blockers = []
    for category, amount in ranked:
        if amount <= 0:
            continue
        delay = int((amount / pace).to_integral_value(rounding="ROUND_HALF_UP")) if pace > 0 else 0
        hint = CATEGORY_HINTS.get(category, "Эта статья съедает темп накопления")
        if delay > 0:
            hint = f"{hint}. За месяц это около {delay} мес. отчислений"
        blockers.append({"category": category, "amount": rub(amount), "hint": hint})
    return blockers
