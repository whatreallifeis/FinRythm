"""CSV-выписка → строки → данные пользователя: формат, отказы, регулярные поступления и повторы."""

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from app.core import detect_income_rules
from app.ingest import parse_csv, state_from_csv
from app.models import Operation

AS_OF = dt.date(2026, 9, 26)
PRESETS = Path(__file__).resolve().parents[3] / "frontend" / "src" / "features" / "import" / "presets"


def test_parse_accepts_bank_formats():
    text = "﻿merchant;amount;date;category\nЯрче;-1 450,50;05.09.26;food\nСтипендия;3400;2026-09-25;other\n"
    rows, rejected = parse_csv(text)
    assert rejected == []
    assert [(r.date, r.amount, r.merchant) for r in rows] == [
        (dt.date(2026, 9, 5), Decimal("-1450.50"), "Ярче"),
        (dt.date(2026, 9, 25), Decimal("3400"), "Стипендия"),
    ]
    assert rows[0].row == 2  # номера строк файла: заголовок — строка 1


def test_parse_reports_bad_rows_by_file_line():
    rows, rejected = parse_csv(
        "date,amount,category,merchant\n2026-09-27,-540,food,Ярче\n31.02.2026,-1,food,X\n"
    )
    assert len(rows) == 1
    assert [(r.row, r.message) for r in rejected] == [(3, "Дата в формате ГГГГ-ММ-ДД или ДД.ММ.ГГГГ.")]


def test_parse_missing_columns():
    rows, rejected = parse_csv("date,amount\n2026-09-01,-1\n")
    assert rows == []
    assert "не хватает колонок: category, merchant" in rejected[0].message


def _op(day: dt.date, amount: str, merchant: str) -> Operation:
    return Operation(id=f"{day}-{merchant}", date=day, amount=Decimal(amount), merchant=merchant)


def test_income_series_needs_same_day_amount_and_months_in_a_row():
    ops = [
        _op(dt.date(2026, 8, 25), "3400", "Стипендия СФУ"),
        _op(dt.date(2026, 9, 25), "3400", "Стипендия СФУ"),
        # переводы через СБП на разные суммы и в разные дни — не регулярный доход
        _op(dt.date(2026, 8, 6), "6500", "Пополнение СБП"),
        _op(dt.date(2026, 9, 19), "7500", "Пополнение СБП"),
        # одна и та же сумма, но через месяц — не «каждый месяц»
        _op(dt.date(2026, 7, 10), "1000", "Кэшбэк"),
        _op(dt.date(2026, 9, 10), "1000", "Кэшбэк"),
    ]
    rules = detect_income_rules(ops)
    assert [(r.title, r.amount, r.day_of_month) for r in rules] == [("Стипендия СФУ", Decimal("3400"), 25)]


def test_full_statement_keeps_repeated_rides_and_finds_regular_income():
    text = (PRESETS / "student.csv").read_text(encoding="utf-8")
    state, result = state_from_csv(text, Decimal("4092"), AS_OF)

    # две поездки на автобусе за 48 ₽ в один день — две операции, а не дубликат
    assert result.imported == 84 and result.rejected == []
    assert len({op.id for op in state.transactions}) == 84
    assert {i.title for i in state.incomes} == {"Пополнение СБП от Ирины К.", "Стипендия СФУ"}
    bills = {op.merchant for op in state.transactions if op.is_recurring and op.amount < 0}
    assert bills == {"Sota Virtual", "Оплата общежития СФУ", "Оплата услуг mBank.t2"}
    # зачисления из найденных серий тоже помечены регулярными
    regular_income = {op.merchant for op in state.transactions if op.is_recurring and op.amount > 0}
    assert regular_income == {"Пополнение СБП от Ирины К.", "Стипендия СФУ"}
    assert state.balance == Decimal("4092")
    assert "регулярных поступлений: 2" in result.warnings[-1]


def test_same_merchant_on_different_days_is_not_a_subscription():
    """Две покупки в Steam 9 августа и 18 сентября на близкие суммы — разовые траты."""
    text = (PRESETS / "freelance.csv").read_text(encoding="utf-8")
    state, _ = state_from_csv(text, Decimal("2300"), AS_OF)
    steam = [op for op in state.transactions if op.merchant == "Steam Purchase"]
    assert len(steam) == 2 and not any(op.is_recurring for op in steam)


@pytest.mark.parametrize(
    ("name", "incomes", "bills"),
    [
        ("student", 2, 3),
        ("worker", 2, 5),
        ("freelance", 1, 4),
        ("junior", 1, 7),
    ],
)
def test_every_preset_loads_cleanly(name, incomes, bills):
    """Каждая готовая выписка загружается без отказов, регулярное находится целиком."""
    state, result = state_from_csv(
        (PRESETS / f"{name}.csv").read_text(encoding="utf-8"), Decimal("5000"), AS_OF
    )
    assert result.rejected == []
    assert len(state.incomes) == incomes
    assert len({op.merchant for op in state.transactions if op.is_recurring and op.amount < 0}) == bills
