"""Порт разбора CSV фронтенда (frontend/src/shared/lib/csv.ts и csvRowSchema в ветке front).

Нужен, чтобы e2e отправляли в API ровно те строки, что отправил бы фронтенд.
"""

import math
import re

CATEGORIES = {"food", "transport", "subscriptions", "entertainment", "health", "education", "rent", "other"}
REQUIRED = ["date", "amount", "category", "merchant"]


def split_line(line: str) -> list[str]:
    cells, current, quoted, i = [], "", False, 0
    while i < len(line):
        char = line[i]
        if char == '"':
            if quoted and i + 1 < len(line) and line[i + 1] == '"':
                current += '"'
                i += 1
            else:
                quoted = not quoted
        elif char == "," and not quoted:
            cells.append(current.strip())
            current = ""
        else:
            current += char
        i += 1
    cells.append(current.strip())
    return cells


def _number(text: str | None) -> float:
    if not text:
        return math.nan
    try:
        return float(text)
    except ValueError:
        return math.nan


def parse_csv(text: str) -> tuple[list[dict], list[tuple[int, str]]]:
    """(строки для API, ошибки разбора с номером строки файла — заголовок = 1)."""
    lines = [line.strip() for line in re.split(r"\r?\n", text) if line.strip()]
    header = [h.lower() for h in split_line(lines[0])]
    index = {c: header.index(c) for c in REQUIRED}
    rows, errors = [], []
    for number, line in enumerate(lines[1:], start=2):
        cells = split_line(line)

        def cell(name: str, cells: list[str] = cells) -> str | None:
            return cells[index[name]] if index[name] < len(cells) else None

        raw = cell("amount")
        amount = _number(None if raw is None else re.sub(r"\s", "", raw).replace(",", ".", 1))
        date, merchant = cell("date") or "", cell("merchant") or ""
        category = cell("category") or "other"
        problems = []
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            problems.append("дата должна быть в формате ГГГГ-ММ-ДД")
        if not math.isfinite(amount):
            problems.append("сумма должна быть числом")
        elif amount == 0:
            problems.append("сумма не может быть нулевой")
        if not merchant:
            problems.append("не указано описание операции")
        if problems:
            errors.append((number, "; ".join(problems)))
            continue
        rows.append(
            {
                "date": date,
                "amount": amount,
                "category": category if category in CATEGORIES else "other",
                "merchant": merchant,
            }
        )
    return rows, errors
