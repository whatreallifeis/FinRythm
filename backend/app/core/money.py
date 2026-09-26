"""Утилиты для денег: округление и форматирование. Только Decimal."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
RUB = Decimal("1")
NBSP = "\u00a0"
MINUS = "\u2212"


def to_money(x: Decimal | int | str) -> Decimal:
    """До копеек, ROUND_HALF_UP."""
    return Decimal(str(x)).quantize(CENT, ROUND_HALF_UP)


def floor_rub(x: Decimal | int | str) -> Decimal:
    return Decimal(str(x)).quantize(RUB, ROUND_FLOOR)


def ceil_rub(x: Decimal | int | str) -> Decimal:
    return Decimal(str(x)).quantize(RUB, ROUND_CEILING)


def fmt_num(x: Decimal | int | str) -> str:
    """«9 800», «785,10», «−700»: неразрывный пробел между разрядами, копейки только если не .00."""
    d = to_money(x)
    sign = MINUS if d < 0 else ""
    rubles, _, kopecks = f"{abs(d):f}".partition(".")
    groups = []
    while len(rubles) > 3:
        groups.insert(0, rubles[-3:])
        rubles = rubles[:-3]
    groups.insert(0, rubles)
    text = NBSP.join(groups)
    if kopecks and kopecks != "00":
        text += "," + kopecks
    return sign + text


def fmt_rub(x: Decimal | int | str) -> str:
    """«9 800 ₽», «785,10 ₽»."""
    return f"{fmt_num(x)} ₽"


def days_word(n: int) -> str:
    """«1 день», «3 дня», «14 дней»."""
    if n % 10 == 1 and n % 100 != 11:
        word = "день"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = "дня"
    else:
        word = "дней"
    return f"{n} {word}"
