"""SF3: mark_recurring — признак is_recurring у регулярных расходов."""

import datetime as dt
from decimal import Decimal

from app.core import load_demo_state, mark_recurring
from app.models import Operation


def _op(i: int, day: dt.date, amount: str, merchant: str, recurring: bool = False) -> Operation:
    return Operation(id=f"t{i}", date=day, amount=amount, merchant=merchant, is_recurring=recurring)


def _flags(ops: list[Operation]) -> dict[str, bool]:
    return {op.id: op.is_recurring for op in ops}


def test_demo_everyday_spending_stays_not_recurring():
    """В ветке front после импорта «Супермаркет», «Доставка еды» и «Кинотеатр» становились платежами."""
    state = load_demo_state()
    marked = mark_recurring(state.transactions)

    assert _flags(marked) == _flags(state.transactions)


def test_monthly_stable_amount_is_recurring():
    ops = [
        _op(1, dt.date(2026, 7, 3), "-500", "Спортзал"),
        _op(2, dt.date(2026, 8, 3), "-520", "Спортзал"),
        _op(3, dt.date(2026, 9, 3), "-480", "спортзал "),
    ]
    assert all(op.is_recurring for op in mark_recurring(ops))


def test_amounts_within_10_percent_are_recurring():
    ops = [
        _op(1, dt.date(2026, 8, 3), "-500", "Спортзал"),
        _op(2, dt.date(2026, 9, 3), "-550", "Спортзал"),
    ]
    assert all(op.is_recurring for op in mark_recurring(ops))


def test_amounts_beyond_10_percent_are_not_recurring():
    ops = [
        _op(1, dt.date(2026, 8, 3), "-500", "Спортзал"),
        _op(2, dt.date(2026, 9, 3), "-560", "Спортзал"),
    ]
    assert not any(op.is_recurring for op in mark_recurring(ops))


def test_weekly_purchases_are_not_monthly_bills():
    ops = [
        _op(i, dt.date(2026, 8, 1) + dt.timedelta(weeks=i), "-700", "Пятёрочка")
        for i in range(8)  # 1 августа … 19 сентября, одинаковая сумма
    ]
    assert not any(op.is_recurring for op in mark_recurring(ops))


def test_single_month_is_not_recurring():
    assert not mark_recurring([_op(1, dt.date(2026, 9, 3), "-500", "Спортзал")])[0].is_recurring


def test_keywords_mark_even_single_operation():
    ops = [
        _op(1, dt.date(2026, 9, 1), "-12000", "Аренда квартиры"),
        _op(2, dt.date(2026, 9, 2), "-649", "Онлайн-кинотеатр"),
        _op(3, dt.date(2026, 9, 3), "-590", "Мобильная связь"),
        _op(4, dt.date(2026, 9, 4), "-1600", "Кинотеатр"),  # поход в кино — разовая трата
    ]
    assert [op.is_recurring for op in mark_recurring(ops)] == [True, True, True, False]


def test_incomes_are_never_marked_and_flags_are_kept():
    ops = [
        _op(1, dt.date(2026, 8, 5), "8000", "Стипендия"),
        _op(2, dt.date(2026, 9, 5), "8000", "Стипендия"),
        _op(3, dt.date(2026, 9, 7), "-300", "Кофейня", recurring=True),
    ]
    marked = mark_recurring(ops)

    assert [op.is_recurring for op in marked] == [False, False, True]


def test_input_is_not_mutated():
    ops = [_op(1, dt.date(2026, 9, 1), "-12000", "Аренда")]
    marked = mark_recurring(ops)

    assert marked[0].is_recurring is True
    assert ops[0].is_recurring is False
    assert marked[0].amount == Decimal("-12000")
