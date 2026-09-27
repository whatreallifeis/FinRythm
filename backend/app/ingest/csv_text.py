"""CSV-выписка → строки импорта → данные пользователя.

Фронтенд разбирает CSV сам и присылает строки JSON-ом; этот модуль нужен, чтобы тот же файл можно было
прогнать на сервере и в консоли (scripts/csv_report.py): получить из выписки все посчитанные числа
без браузера.

Формат — как во фронтенде: колонки date, amount, category, merchant в любом порядке, разделитель —
запятая или точка с запятой. Дата — ГГГГ-ММ-ДД или ДД.ММ.ГГГГ (ДД.ММ.ГГ, как в банковской выписке).
Сумма — «-1 450,50»: пробелы и запятая допустимы; расход со знаком минус.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from decimal import Decimal, InvalidOperation

from app.core.recurring import detect_income_rules
from app.core.runway_calendar import normalize_merchant
from app.ingest.apply_import import apply_import
from app.models import ImportResult, ImportRow, RejectedRow, UserState

REQUIRED = ("date", "amount", "category", "merchant")
_DMY = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})$")


def _date(text: str) -> dt.date | None:
    text = text.strip()
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        pass
    if match := _DMY.match(text):
        day, month, year = (int(part) for part in match.groups())
        year += 2000 if year < 100 else 0
        try:
            return dt.date(year, month, day)
        except ValueError:
            return None
    return None


def _amount(text: str) -> Decimal | None:
    cleaned = re.sub(r"[\s ₽]", "", text).replace("−", "-").replace(",", ".")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def parse_csv(text: str) -> tuple[list[ImportRow], list[RejectedRow]]:
    """Строки выписки и отказы с номерами строк файла (заголовок — строка 1)."""
    text = text.lstrip("﻿")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return [], [RejectedRow(row=1, message="Файл пустой.")]
    delimiter = ";" if lines[0].count(";") > lines[0].count(",") else ","
    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter)
    header = [cell.strip().lower() for cell in next(reader)]
    missing = [name for name in REQUIRED if name not in header]
    if missing:
        return [], [
            RejectedRow(
                row=1,
                message=f"В заголовке не хватает колонок: {', '.join(missing)}. "
                f"Нужны: {', '.join(REQUIRED)}.",
            )
        ]
    index = {name: header.index(name) for name in REQUIRED}

    rows: list[ImportRow] = []
    rejected: list[RejectedRow] = []
    for number, cells in enumerate(reader, start=2):
        cell = {name: (cells[i].strip() if i < len(cells) else "") for name, i in index.items()}
        date = _date(cell["date"])
        amount = _amount(cell["amount"])
        if date is None:
            rejected.append(RejectedRow(row=number, message="Дата в формате ГГГГ-ММ-ДД или ДД.ММ.ГГГГ."))
            continue
        if amount is None:
            rejected.append(RejectedRow(row=number, message="Сумма должна быть числом."))
            continue
        rows.append(
            ImportRow(
                date=date,
                amount=amount,
                category=cell["category"] or "other",
                merchant=cell["merchant"],
                row=number,
            )
        )
    return rows, rejected


def replace_dataset(
    rows: list[ImportRow], balance: Decimal | None, as_of: dt.date
) -> tuple[UserState, ImportResult]:
    """Новая выписка целиком: операции, найденные в ней регулярные расходы и поступления, баланс.

    Прежние операции, автоплатежи, цели и история диалогов не переносятся — это другой набор данных.
    """
    state, result = apply_import(UserState(balance=balance), rows, as_of, keep_repeats=True)
    incomes = detect_income_rules(state.transactions)
    regular = {normalize_merchant(inc.title) for inc in incomes}
    # Зачисления из найденных серий тоже регулярные — так их видно в календаре и в справке.
    transactions = [
        op.model_copy(update={"is_recurring": True})
        if op.amount > 0 and normalize_merchant(op.merchant) in regular
        else op
        for op in state.transactions
    ]
    state = state.model_copy(update={"incomes": incomes, "transactions": transactions})
    bills = len(
        {normalize_merchant(op.merchant) for op in state.transactions if op.is_recurring and op.amount < 0}
    )
    found = [
        f"регулярных платежей: {bills}" if bills else None,
        f"регулярных поступлений: {len(incomes)}" if incomes else None,
    ]
    found = [item for item in found if item]
    warnings = list(result.warnings)
    if found:
        warnings.append(f"Найдено {', '.join(found)} — они добавлены в календарь. Проверьте их названия.")
    elif result.imported:
        warnings.append(
            "Регулярных поступлений в выписке не нашлось — календарь до поступления не построить. "
            "Нужна выписка хотя бы за два месяца."
        )
    return state, result.model_copy(update={"warnings": warnings})


def state_from_csv(text: str, balance: Decimal | None, as_of: dt.date) -> tuple[UserState, ImportResult]:
    """CSV-текст → данные пользователя. Отказы разбора и импорта — вместе, по номерам строк файла."""
    rows, bad = parse_csv(text)
    state, result = replace_dataset(rows, balance, as_of)
    # apply_import нумерует строки по месту в списке — возвращаем номера строк файла.
    renumbered = [
        item.model_copy(update={"row": rows[item.row - 1].row or item.row}) for item in result.rejected
    ]
    rejected = sorted([*bad, *renumbered], key=lambda item: item.row)
    return state, result.model_copy(update={"rejected": rejected})
