"""Поиск регулярных платежей и подписок."""

from __future__ import annotations

import hashlib
from decimal import Decimal

from app.core.runway_calendar import normalize_merchant
from app.models import IncomeRule, Operation, RecurringItem, Transaction

# Слова, по которым расход регулярный сразу. Голого «кинотеатр» нет: поход в кино — разовая трата (issue #12).
RECURRING_WORDS = ("подписк", "аренд", "проезд", "связь", "интернет", "онлайн-кинотеатр", "музык", "мобильн")
AMOUNT_TOLERANCE = Decimal("0.10")  # разброс сумм — не больше 10% от меньшей


def detect_recurring(transactions: list[Transaction]) -> list[RecurringItem]:
    return []


DAY_TOLERANCE = 3  # списывается примерно в одно число месяца: разброс не больше 3 дней


def _looks_monthly(group: list[Operation]) -> bool:
    """В двух и более месяцах, не чаще раза в месяц, суммы отличаются не больше чем на 10%,
    число месяца — не больше чем на 3 дня (две покупки в одном магазине 9 и 18 числа — не подписка)."""
    months = [op.date.strftime("%Y-%m") for op in group]
    if len(set(months)) < 2 or len(set(months)) != len(months):
        return False
    amounts = [-op.amount for op in group]
    days = [op.date.day for op in group]
    return (
        max(amounts) - min(amounts) <= min(amounts) * AMOUNT_TOLERANCE
        and max(days) - min(days) <= DAY_TOLERANCE
    )


def mark_recurring(transactions: list[Operation]) -> list[Operation]:
    """Копия списка с признаком is_recurring у регулярных расходов. Уже стоящий признак не снимается.

    В ветке front регулярным становился любой магазин из двух месяцев («Супермаркет», «Доставка еды»),
    и календарь считал их обязательными платежами (issue #12).
    """
    groups: dict[str, list[Operation]] = {}
    for op in transactions:
        if op.amount < 0:
            groups.setdefault(normalize_merchant(op.merchant), []).append(op)
    recurring_ids: set[str] = set()
    for key, group in groups.items():
        if any(word in key for word in RECURRING_WORDS) or _looks_monthly(group):
            recurring_ids.update(op.id for op in group)
    return [
        op.model_copy(update={"is_recurring": True}) if op.id in recurring_ids and not op.is_recurring else op
        for op in transactions
    ]


# ---------------------------------------------------------------- регулярные поступления

INCOME_AMOUNT_SPREAD = Decimal("1.15")  # суммы поступления отличаются не больше чем на 15%
INCOME_DAY_SPREAD = 3  # и приходят примерно в одно число — разброс до 3 дней


def _months_in_a_row(group: list[Operation]) -> bool:
    months = sorted(op.date.year * 12 + op.date.month for op in group)
    steps = zip(months, months[1:], strict=False)
    return len(set(months)) == len(months) and all(b - a == 1 for a, b in steps)


def detect_income_rules(transactions: list[Operation]) -> list[IncomeRule]:
    """Поступления, которые повторяются каждый месяц: стипендия, зарплата, перевод от родителей.

    Серия — одно описание, два и более месяца подряд, не чаще раза в месяц, суммы отличаются не больше
    чем на 15%, число месяца — не больше чем на 3 дня. Нерегулярные пополнения через СБП с разными
    суммами в серию не попадают. Правило то же, что во фронтенде (mock/recurring.ts).
    """
    groups: dict[str, list[Operation]] = {}
    for op in transactions:
        if op.amount > 0 and op.merchant.strip():
            groups.setdefault(normalize_merchant(op.merchant), []).append(op)

    rules: list[IncomeRule] = []
    for key, group in sorted(groups.items()):
        if len(group) < 2 or not _months_in_a_row(group):
            continue
        amounts = [op.amount for op in group]
        days = [op.date.day for op in group]
        if max(amounts) > min(amounts) * INCOME_AMOUNT_SPREAD or max(days) - min(days) > INCOME_DAY_SPREAD:
            continue
        last = max(group, key=lambda op: op.date)
        rules.append(
            IncomeRule(
                id="inc-" + hashlib.sha1(key.encode()).hexdigest()[:10],
                title=last.merchant.strip()[:100],
                amount=last.amount,
                day_of_month=last.date.day,
            )
        )
    return rules
