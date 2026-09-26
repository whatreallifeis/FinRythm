"""Обёртка объяснимости Explained для расчётов нового API (routes.py ветки front)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from app.models import CalcStep, DataQuality, Explained, Operation

COMMON_LIMITS = [
    "Расчёт сделан по загруженным данным. Банковские счета не подключены.",
    "Это не инвестиционная рекомендация и не операция с деньгами. Решение остаётся за вами.",
]

MONTHS_GEN = (
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


def coverage_days(transactions: list[Operation], as_of: dt.date) -> int:
    """За сколько дней есть операции: от самой ранней (не позже as_of) до as_of включительно."""
    dates = [op.date for op in transactions if op.date <= as_of]
    return (as_of - min(dates)).days + 1 if dates else 0


def human_date(value: dt.date) -> str:
    """«5 октября»."""
    return f"{value.day} {MONTHS_GEN[value.month - 1]}"


def step(label: str, formula: str, value: Decimal | int) -> CalcStep:
    return CalcStep(label=label, formula=formula, value=Decimal(value))


def explained(
    result: dict[str, Any],
    *,
    coverage: int,
    assumptions: list[str] | None = None,
    calculation: list[CalcStep] | None = None,
    limitations: list[str] | None = None,
    missing: list[str] | None = None,
) -> Explained:
    """sufficient = нет недостающих данных. Без limitations — общие оговорки COMMON_LIMITS."""
    return Explained(
        result=result,
        assumptions=assumptions or [],
        calculation=calculation or [],
        limitations=list(COMMON_LIMITS if limitations is None else limitations),
        data_quality=DataQuality(sufficient=not missing, missing=missing or [], coverage_days=coverage),
    )
