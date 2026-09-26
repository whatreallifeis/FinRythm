"""Поиск регулярных платежей и подписок. Заглушка S1."""

from __future__ import annotations

from app.models import RecurringItem, Transaction


def detect_recurring(transactions: list[Transaction]) -> list[RecurringItem]:
    return []
