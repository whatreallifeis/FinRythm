"""Дата расчёта. В тестах подменяется, чтобы цифры не зависели от календаря машины."""

from datetime import date

_override: date | None = None


def today() -> date:
    return _override or date.today()


def set_today(value: date | None) -> None:
    global _override
    _override = value
