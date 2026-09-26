"""Проверка чисел в ответе помощника (A5): каждое число в тексте должно быть в результатах расчёта.

Разрешены числа из Explained (result без самого текста ответа, шаги расчёта с формулами, допущения),
из вопроса пользователя и из фрагментов базы знаний, по которым отвечает справочник; плюс 0, 1, 100.
Даты разрешают день, месяц и год; доли 0..1 — ещё и в процентах. Знак не важен («−10 618 ₽» = -10618).
Число из текста совпадает, если равно разрешённому или его округлению до рубля.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.models import Explained

_NUMBER = re.compile(
    r"(?<![\w.,\-])\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d+)?(?![\w])|(?<![\w.,\-])\d+(?:[.,]\d+)?(?![\w])"
)
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
ALWAYS_ALLOWED = {Decimal(0), Decimal(1), Decimal(100)}


def extract_numbers(text: str) -> list[Decimal]:
    """Все числа из текста: «18 430», «785,10», «14\u00a0900» → Decimal (без знака)."""
    out = []
    for raw in _NUMBER.findall(text):
        try:
            out.append(Decimal(re.sub(r"[ \u00a0]", "", raw).replace(",", ".")))
        except InvalidOperation:
            continue
    return out


def _from_value(value: Any) -> Iterable[Decimal]:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int | float | Decimal):
        number = abs(Decimal(str(value)))
        yield number
        if 0 < number <= 1:
            yield number * 100  # доля → проценты
    elif isinstance(value, dt.date):
        yield from (Decimal(value.day), Decimal(value.month), Decimal(value.year))
    elif isinstance(value, str):
        if match := _ISO_DATE.match(value):
            yield from (Decimal(int(part)) for part in match.groups())
        else:
            yield from extract_numbers(value)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _from_value(item)
    elif isinstance(value, list | tuple | set):
        for item in value:
            yield from _from_value(item)


def allowed_numbers(explained: Explained, *, question: str = "", facts: Iterable[Any] = ()) -> set[Decimal]:
    """Числа, которые можно упоминать в ответе: из расчёта, вопроса и фактов (результаты core, тексты
    источников), но не из самого ответа."""
    result = {k: v for k, v in explained.result.items() if k != "text"}
    allowed = set(ALWAYS_ALLOWED)
    allowed.update(_from_value(result))
    allowed.update(_from_value([step.model_dump() for step in explained.calculation]))
    allowed.update(_from_value(explained.assumptions))
    allowed.update(extract_numbers(question))
    allowed.update(_from_value(list(facts)))
    return allowed


def _matches(number: Decimal, allowed: set[Decimal]) -> bool:
    if number in allowed:
        return True
    return any(
        number == a.quantize(Decimal(1), ROUND_HALF_UP) or number == a.quantize(Decimal(1), ROUND_FLOOR)
        for a in allowed
    )


def check_numbers(text: str, allowed: set[Decimal]) -> tuple[bool, list[Decimal]]:
    """(всё в порядке?, числа из текста, которых нет среди разрешённых)."""
    bad = [n for n in extract_numbers(text) if not _matches(n, allowed)]
    return not bad, bad
