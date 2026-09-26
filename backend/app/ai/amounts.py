"""Сумма покупки из текста вопроса: «3000», «3 000», «3к», «2,5 тыс», «14 900 ₽», «4900р»."""

from __future__ import annotations

import re
from decimal import Decimal

_MONTHS = r"январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр"

_AMOUNT = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:[ \u00a0]\d{3})+|\d+)(?:[.,](\d{1,2}))?(?![\d])"
    r"(?:\s*(к(?![а-яё])|k(?![a-z])|тыс[а-яё]*\.?))?"
    r"(?:\s*(₽|руб[а-яё]*\.?|р\.|р(?![а-яё])))?",
    re.IGNORECASE,
)
_YEAR_AFTER = re.compile(r"^\s*(?:г\.|г\b|год)", re.IGNORECASE)
_MONTH_BEFORE = re.compile(rf"(?:{_MONTHS})[а-яё]*\s*$", re.IGNORECASE)

# Без «₽» и «к» считаем суммой только числа от 50: «5 октября», «на 2 дня» — не покупка.
MIN_PLAIN_AMOUNT = Decimal(50)


def _is_year(text: str, match: re.Match[str], value: Decimal) -> bool:
    if not (1900 <= value <= 2100) or match.group(2):
        return False
    return bool(_YEAR_AFTER.match(text[match.end() :]) or _MONTH_BEFORE.search(text[: match.start()]))


def extract_amount(text: str) -> Decimal | None:
    """Сумма из вопроса или None. Если сумм несколько, берётся последняя с «₽»/«к», иначе последняя."""
    marked: list[Decimal] = []
    plain: list[Decimal] = []
    for match in _AMOUNT.finditer(text):
        whole, fraction, thousands, currency = match.groups()
        value = Decimal(re.sub(r"[ \u00a0]", "", whole) + (f".{fraction}" if fraction else ""))
        if thousands:
            value *= 1000
        if value <= 0:
            continue
        if thousands or currency:
            marked.append(value)
        elif value >= MIN_PLAIN_AMOUNT and not _is_year(text, match, value):
            plain.append(value)
    if marked:
        return marked[-1]
    return plain[-1] if plain else None
