"""Импорт строк, которые прислал фронтенд (import_transactions из routes.py ветки front).

CSV разбирает фронтенд, сюда приходят готовые строки ImportRow. Номер строки — с 1.
Отличие от ветки front (issue #12): номер карты ищется в любом месте описания, а не только
когда всех цифр в нём 13–19.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from decimal import Decimal

from pydantic import ValidationError

from app.core.money import to_money
from app.core.recurring import mark_recurring
from app.models import CATEGORY_IDS, ImportResult, ImportRow, Operation, RejectedRow, UserState

CARD_RE = re.compile(r"(?:\d[ -]?){13,19}")  # 13+ цифр подряд, можно через пробел или дефис
MAX_AMOUNT = Decimal("10000000000")  # 10 млрд: Operation хранит не больше 12 знаков
MAX_MERCHANT = 200


def _key(date: dt.date, amount: Decimal, merchant: str) -> tuple[str, Decimal, str]:
    """Дубликат — та же дата, сумма и магазин (без учёта регистра)."""
    return date.isoformat(), to_money(amount), merchant.strip().casefold()


def _op_id(key: tuple[str, Decimal, str]) -> str:
    date, amount, merchant = key
    return "imp-" + hashlib.sha1(f"{date}|{amount}|{merchant}".encode()).hexdigest()[:12]


def _problem(row: ImportRow, as_of: dt.date) -> str | None:
    merchant = row.merchant.strip()
    if row.amount == 0:
        return "Сумма не может быть нулевой."
    if abs(row.amount) >= MAX_AMOUNT:
        return "Сумма слишком большая — проверьте, нет ли лишних цифр."
    if row.date > as_of:
        return "Дата операции в будущем — такой операции ещё не было."
    if not merchant:
        return "Не указано описание операции."
    if CARD_RE.search(merchant):
        return "Похоже на номер карты. Такие данные загружать нельзя."
    if len(merchant) > MAX_MERCHANT:
        return f"Описание длиннее {MAX_MERCHANT} символов — сократите его."
    return None


def apply_import(state: UserState, rows: list[ImportRow], as_of: dt.date) -> tuple[UserState, ImportResult]:
    """Добавить строки к операциям пользователя. Исходный state не меняется.

    Отказ строки: нулевая сумма, дата в будущем, нет описания, номер карты.
    Неизвестная категория → «other» с предупреждением. Дубликаты пропускаются с предупреждением.
    В конце признак регулярности пересчитывается по всем операциям (mark_recurring).
    """
    transactions = list(state.transactions)
    existing = {_key(op.date, op.amount, op.merchant) for op in transactions}
    imported = 0
    rejected: list[RejectedRow] = []
    warnings: list[str] = []

    for index, row in enumerate(rows, start=1):
        message = _problem(row, as_of)
        if message:
            rejected.append(RejectedRow(row=index, message=message))
            continue
        key = _key(row.date, row.amount, row.merchant)
        if key in existing:
            warnings.append(f"Строка {index}: такая операция уже есть, пропущена.")
            continue
        category = row.category if row.category in CATEGORY_IDS else "other"
        try:
            op = Operation(
                id=_op_id(key),
                date=row.date,
                amount=key[1],
                category=category,
                merchant=row.merchant.strip(),
            )
        except ValidationError:
            message = "Строку не удалось прочитать — проверьте сумму и дату."
            rejected.append(RejectedRow(row=index, message=message))
            continue
        if category != row.category:
            warnings.append(f"Строка {index}: неизвестная категория «{row.category}» заменена на «другое».")
        transactions.append(op)
        existing.add(key)
        imported += 1

    if imported == 0 and not rejected:
        warnings.append("Новых операций нет.")
    new_state = state.model_copy(update={"transactions": mark_recurring(transactions)})
    return new_state, ImportResult(imported=imported, rejected=rejected, warnings=warnings)
