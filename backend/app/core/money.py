"""Утилиты для денег: округление и форматирование. Только Decimal."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
RUB = Decimal("1")


def to_money(x: Decimal | int | str) -> Decimal:
    """До копеек, ROUND_HALF_UP."""
    return Decimal(str(x)).quantize(CENT, ROUND_HALF_UP)


def floor_rub(x: Decimal | int | str) -> Decimal:
    return Decimal(str(x)).quantize(RUB, ROUND_FLOOR)


def ceil_rub(x: Decimal | int | str) -> Decimal:
    return Decimal(str(x)).quantize(RUB, ROUND_CEILING)


def fmt_rub(x: Decimal | int | str) -> str:
    """«9 800 ₽», «785,10 ₽» — заглушка, полная реализация в S2."""
    return f"{to_money(x)} ₽"
