"""SF2: демо-профиль студента (data/demo/student.json) — сценарий из handoff.md ветки front."""

import datetime as dt
from decimal import Decimal

from app.core import DEMO_AS_OF, load_demo_state
from app.models import CATEGORY_IDS, UserState


def test_demo_state_matches_handoff():
    state = load_demo_state()

    assert isinstance(state, UserState)
    assert DEMO_AS_OF == dt.date(2026, 9, 26)
    assert state.balance == Decimal("18430")
    incomes = {i.title: (i.amount, i.day_of_month) for i in state.incomes}
    assert incomes == {"Стипендия": (Decimal("8000"), 5), "Подработка": (Decimal("25000"), 10)}
    assert [g.id for g in state.goals] == ["g-1", "g-2"]
    assert state.goals[1].deadline is None
    assert state.history == []


def test_demo_transactions_are_valid():
    state = load_demo_state()
    ops = state.transactions

    assert len(ops) == 25
    assert len({op.id for op in ops}) == len(ops)
    assert all(op.category in CATEGORY_IDS for op in ops)
    assert all(op.date <= DEMO_AS_OF for op in ops)
    assert all(op.amount != 0 for op in ops)
    # Регулярные расходы — основа календаря платежей: аренда, подписки, проездной, связь.
    recurring = {op.merchant for op in ops if op.is_recurring and op.amount < 0}
    assert recurring == {
        "Аренда комнаты",
        "Музыкальная подписка",
        "Онлайн-кинотеатр",
        "Проездной",
        "Мобильная связь",
    }
    # Аномалия для обзора — концертные билеты 14 900 ₽.
    concert = next(op for op in ops if op.id == "t-911")
    assert concert.amount == Decimal("-14900")


def test_load_demo_state_returns_fresh_copy():
    first = load_demo_state()
    first.transactions.clear()
    assert len(load_demo_state().transactions) == 25
