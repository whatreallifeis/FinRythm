from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
RUBLE = Decimal("1")
TIGHT_FLOOR = Decimal("2000")


def D(value: object) -> Decimal:
    return Decimal(str(value))


def rub(value: Decimal) -> float:
    """На границе JSON отдаём число с копейками. Внутри модуля деньги остаются Decimal."""
    return float(value.quantize(CENT, ROUND_HALF_UP))


def whole(value: Decimal) -> float:
    return float(value.quantize(RUBLE, ROUND_HALF_UP))


def floor_ruble(value: Decimal) -> Decimal:
    return value.quantize(RUBLE, ROUND_FLOOR)


def ceil_ruble(value: Decimal) -> Decimal:
    return value.quantize(RUBLE, ROUND_CEILING)


def fmt_rub(value: Decimal) -> str:
    rounded = int(value.quantize(RUBLE, ROUND_HALF_UP))
    sign = "−" if rounded < 0 else ""
    return f"{sign}{abs(rounded):,}".replace(",", " ") + " ₽"
