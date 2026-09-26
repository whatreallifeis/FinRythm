from decimal import Decimal

import pytest
from app.core.money import ceil_rub, days_word, floor_rub, fmt_num, fmt_rub, to_money

NB = "\u00a0"


def test_to_money_half_up():
    assert to_money("785.105") == Decimal("785.11")
    assert to_money(3) == Decimal("3.00")


def test_floor_and_ceil():
    assert floor_rub(Decimal("404.99")) == Decimal(404)
    assert ceil_rub(Decimal("322.01")) == Decimal(323)
    assert floor_rub(Decimal("-0.5")) == Decimal(-1)


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("9800", f"9{NB}800 ₽"),
        ("9800.00", f"9{NB}800 ₽"),
        ("785.10", "785,10 ₽"),
        ("0", "0 ₽"),
        ("10000000", f"10{NB}000{NB}000 ₽"),
        ("-700", "−700 ₽"),
        ("1234.5", f"1{NB}234,50 ₽"),
    ],
)
def test_fmt_rub(value, text):
    assert fmt_rub(Decimal(value)) == text


def test_fmt_num_without_currency():
    assert fmt_num(Decimal("1949")) == f"1{NB}949"


@pytest.mark.parametrize(
    ("n", "text"),
    [
        (1, "1 день"),
        (2, "2 дня"),
        (5, "5 дней"),
        (11, "11 дней"),
        (14, "14 дней"),
        (21, "21 день"),
        (22, "22 дня"),
    ],
)
def test_days_word(n, text):
    assert days_word(n) == text
