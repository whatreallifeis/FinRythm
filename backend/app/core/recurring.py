"""Поиск регулярных платежей и подписок."""

from __future__ import annotations

from decimal import Decimal

from app.core.runway_calendar import normalize_merchant
from app.models import Operation, RecurringItem, Transaction

# Слова, по которым расход регулярный сразу. Голого «кинотеатр» нет: поход в кино — разовая трата (issue #12).
RECURRING_WORDS = ("подписк", "аренд", "проезд", "связь", "интернет", "онлайн-кинотеатр", "музык", "мобильн")
AMOUNT_TOLERANCE = Decimal("0.10")  # разброс сумм — не больше 10% от меньшей


def detect_recurring(transactions: list[Transaction]) -> list[RecurringItem]:
    return []


def _looks_monthly(group: list[Operation]) -> bool:
    """В двух и более месяцах, не чаще раза в месяц, суммы отличаются не больше чем на 10%."""
    months = [op.date.strftime("%Y-%m") for op in group]
    if len(set(months)) < 2 or len(set(months)) != len(months):
        return False
    amounts = [-op.amount for op in group]
    return max(amounts) - min(amounts) <= min(amounts) * AMOUNT_TOLERANCE


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
