"""Календарь до следующего поступления и проверка покупки.

Один расчёт обслуживает и «хватит ли до стипендии», и «могу купить это сегодня»:
иначе дневной лимит и проверка покупки разойдутся.
"""

from datetime import date, timedelta
from decimal import Decimal

from app.money import TIGHT_FLOOR, D, floor_ruble, fmt_rub, rub

MONTHS = (
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
)


def next_on_day(today: date, day_of_month: int) -> date:
    year, month = today.year, today.month
    candidate = _clamp(year, month, day_of_month)
    if candidate <= today:
        month += 1
        if month == 13:
            month = 1
            year += 1
        candidate = _clamp(year, month, day_of_month)
    return candidate


def _clamp(year: int, month: int, day: int) -> date:
    # 31-е в коротком месяце сдвигается на последний день, а не теряется.
    last = _last_day(year, month)
    return date(year, month, min(day, last))


def _last_day(year: int, month: int) -> int:
    if month == 12:
        return (date(year + 1, 1, 1) - timedelta(days=1)).day
    return (date(year, month + 1, 1) - timedelta(days=1)).day


def human_date(value: date) -> str:
    return f"{value.day} {MONTHS[value.month - 1]}"


def recurring_bills(transactions: list[dict]) -> list[tuple[str, Decimal, int]]:
    """Регулярный расход становится будущим платежом в тот же день месяца."""
    latest: dict[str, tuple[date, str, Decimal]] = {}
    for row in transactions:
        if not row.get("isRecurring"):
            continue
        amount = D(row["amount"])
        if amount >= 0:
            continue
        when = date.fromisoformat(row["date"])
        key = " ".join(row["merchant"].casefold().split())
        previous = latest.get(key)
        if previous is None or when >= previous[0]:
            latest[key] = (when, row["merchant"], -amount)
    return [(title, amount, when.day) for when, title, amount in latest.values()]


def planned_events(incomes: list[dict], transactions: list[dict], today: date) -> list[dict]:
    events: list[dict] = []
    for title, amount, day in recurring_bills(transactions):
        events.append(
            {"date": next_on_day(today, day), "title": title, "amount": -amount},
        )
    for income in incomes:
        events.append(
            {
                "date": next_on_day(today, int(income["dayOfMonth"])),
                "title": income["title"],
                "amount": D(income["amount"]),
            }
        )
    events.sort(key=lambda item: (item["date"], item["title"]))
    return events


def _status(balance: Decimal) -> str:
    if balance < 0:
        return "shortfall"
    if balance < TIGHT_FLOOR:
        return "tight"
    return "ok"


def simulate(
    *,
    today: date,
    balance: Decimal,
    events: list[dict],
    horizon_end: date,
    impulse: tuple[Decimal, date] | None = None,
) -> list[dict]:
    cursor = balance
    days: list[dict] = []
    current = today
    while current <= horizon_end:
        day_events = [
            {"title": event["title"], "amount": event["amount"]}
            for event in events
            if event["date"] == current
        ]
        if impulse and impulse[1] == current and impulse[0] > 0:
            day_events.append({"title": "Покупка", "amount": -impulse[0]})
        for event in day_events:
            cursor += event["amount"]
        days.append(
            {
                "date": current.isoformat(),
                "events": [{"title": event["title"], "amount": rub(event["amount"])} for event in day_events],
                "balance": rub(cursor),
                "status": _status(cursor),
                "_balance": cursor,
            }
        )
        current += timedelta(days=1)
    return days


def first_income(events: list[dict], after: date) -> dict | None:
    found = next((event for event in events if event["amount"] > 0 and event["date"] > after), None)
    if found is None:
        return None
    return {
        "date": found["date"].isoformat(),
        "title": found["title"],
        "amount": rub(found["amount"]),
        "daysUntil": (found["date"] - after).days,
        "_date": found["date"],
    }


def safe_daily(balance: Decimal, events: list[dict], today: date, until: date) -> Decimal:
    days = max((until - today).days, 1)
    bills = sum(
        (event["amount"] for event in events if event["amount"] < 0 and today < event["date"] < until),
        D(0),
    )
    free = balance + bills
    if free <= 0:
        return D(0)
    return floor_ruble(free / days)


def _summarize(days: list[dict]) -> tuple[int, Decimal]:
    if not days:
        return 0, D(0)
    red = sum(1 for day in days if day["status"] == "shortfall")
    lowest = min(day["_balance"] for day in days)
    return red, lowest


def _public_days(days: list[dict]) -> list[dict]:
    return [
        {"date": day["date"], "events": day["events"], "balance": day["balance"], "status": day["status"]}
        for day in days
    ]


def build_runway(balance: Decimal, incomes: list[dict], transactions: list[dict], today: date) -> dict:
    events = planned_events(incomes, transactions, today)
    horizon_end = events[-1]["date"] if events else today + timedelta(days=14)
    days = simulate(today=today, balance=balance, events=events, horizon_end=horizon_end)
    nxt = first_income(events, today)
    until = nxt["_date"] if nxt else horizon_end
    red, lowest = _summarize(days)
    public_next = None if nxt is None else {key: nxt[key] for key in ("date", "title", "amount", "daysUntil")}
    return {
        "horizonTo": horizon_end.isoformat(),
        "nextIncome": public_next,
        "todaySafeSpend": whole_spend(safe_daily(balance, events, today, until)),
        "lowestBalance": rub(lowest),
        "redDays": red,
        "days": _public_days(days),
        "_events": events,
        "_until": until,
    }


def whole_spend(value: Decimal) -> float:
    return float(value)


def build_impulse(
    balance: Decimal,
    incomes: list[dict],
    transactions: list[dict],
    goals: list[dict],
    today: date,
    amount: Decimal,
) -> dict:
    events = planned_events(incomes, transactions, today)
    horizon_end = events[-1]["date"] if events else today + timedelta(days=14)
    until_event = first_income(events, today)
    until = until_event["_date"] if until_event else horizon_end

    before_days = simulate(today=today, balance=balance, events=events, horizon_end=horizon_end)
    after_days = simulate(
        today=today,
        balance=balance,
        events=events,
        horizon_end=horizon_end,
        impulse=(amount, today),
    )
    red_before, low_before = _summarize(before_days)
    red_after, low_after = _summarize(after_days)
    spend_before = safe_daily(balance, events, today, until)
    spend_after = safe_daily(balance - amount, events, today, until)

    verdict = "ok"
    if low_after < 0:
        verdict = "shortfall"
    elif red_after > red_before or (low_after < TIGHT_FLOOR <= low_before):
        verdict = "wait"

    wait_until = None
    if verdict != "ok":
        for event in events:
            if event["amount"] <= 0 or event["date"] <= today:
                continue
            trial_red, trial_low = _summarize(
                simulate(
                    today=today,
                    balance=balance,
                    events=events,
                    horizon_end=horizon_end,
                    impulse=(amount, event["date"]),
                )
            )
            if trial_low >= 0 and trial_red == 0:
                wait_until = {
                    "date": event["date"].isoformat(),
                    "title": event["title"],
                    "amount": rub(event["amount"]),
                    "daysUntil": (event["date"] - today).days,
                }
                break

    goal_impact = _goal_impact(goals, today, amount)
    hint = _hint(verdict, spend_after, wait_until)
    public_next = (
        None
        if until_event is None
        else {key: until_event[key] for key in ("date", "title", "amount", "daysUntil")}
    )
    return {
        "amount": rub(amount),
        "verdict": verdict,
        "hint": hint,
        "todaySafeSpendBefore": whole_spend(spend_before),
        "todaySafeSpendAfter": whole_spend(spend_after),
        "redDaysBefore": red_before,
        "redDaysAfter": red_after,
        "lowestBalanceAfter": rub(low_after),
        "waitUntil": wait_until,
        "goalImpact": goal_impact,
        "daysAfter": _public_days(after_days),
        "_next": public_next,
    }


def _goal_impact(goals: list[dict], today: date, amount: Decimal) -> dict | None:
    goal = next(
        (item for item in goals if item.get("deadline") and D(item["savedAmount"]) < D(item["targetAmount"])),
        None,
    )
    if goal is None:
        return None
    deadline = date.fromisoformat(goal["deadline"])
    remaining = D(goal["targetAmount"]) - D(goal["savedAmount"])
    days_left = (deadline - today).days
    if remaining <= 0 or days_left <= 0:
        return None
    daily = remaining / Decimal(days_left)
    if daily <= 0:
        return None
    delay = int((amount / daily).to_integral_value(rounding="ROUND_CEILING"))
    return {"goalTitle": goal["title"], "delayDays": max(delay, 1)}


def _hint(verdict: str, spend_after: Decimal, wait_until: dict | None) -> str:
    if verdict == "ok":
        return (
            f"Покупка влезает: дневной лимит станет {fmt_rub(spend_after)}, "
            "обязательные платежи не пострадают."
        )
    if wait_until:
        when = human_date(date.fromisoformat(wait_until["date"]))
        if verdict == "wait":
            return (
                f"Лучше подождать до «{wait_until['title']}» {when}: "
                "тогда покупка не сожмёт дни до поступления."
            )
        return (
            f"Сейчас не влезет: после обязательных платежей баланс уйдёт в минус. "
            f"Подождите «{wait_until['title']}» {when}."
        )
    return "Сейчас не влезет: после обязательных платежей не хватит денег. Покупку лучше отложить."
