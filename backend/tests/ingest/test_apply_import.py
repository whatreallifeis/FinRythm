"""SF4: apply_import — импорт строк, которые прислал фронтенд."""

import datetime as dt
from decimal import Decimal

import pytest
from app.core import DEMO_AS_OF, build_runway, load_demo_state
from app.ingest import apply_import
from app.models import ImportResult, ImportRow, UserState

AS_OF = dt.date(2026, 9, 26)


def _row(amount="-540", merchant="Супермаркет", category="food", date=dt.date(2026, 9, 25)) -> ImportRow:
    return ImportRow(date=date, amount=amount, category=category, merchant=merchant)


def test_front_scenario_card_and_zero_rejected():
    """Тот же набор, что в test_api.py ветки front: одна строка принята, две отклонены."""
    rows = [
        _row(),
        _row(amount="-100", category="other", merchant="4276 1234 5678 9012"),
        _row(amount="0", merchant="Пусто"),
    ]
    state, result = apply_import(UserState(), rows, AS_OF)

    assert isinstance(result, ImportResult)
    assert result.imported == 1
    assert [(r.row, r.message) for r in result.rejected] == [
        (2, "Похоже на номер карты. Такие данные загружать нельзя."),
        (3, "Сумма не может быть нулевой."),
    ]
    op = state.transactions[0]
    assert (op.date, op.amount, op.category, op.merchant, op.is_recurring) == (
        dt.date(2026, 9, 25),
        Decimal("-540.00"),
        "food",
        "Супермаркет",
        False,
    )
    assert op.id.startswith("imp-")


@pytest.mark.parametrize(
    "merchant",
    [
        "4276 1234 5678 9012",
        "4276-1234-5678-9012",
        "Карта 4276123456789012, чек 55",
        "Перевод 4276 1234 5678 9012 от 12.09",  # в ветке front проходило: всего цифр 20
        "Счёт 40817810099910004312",
    ],
)
def test_card_number_anywhere_is_rejected(merchant):
    state, result = apply_import(UserState(), [_row(merchant=merchant)], AS_OF)

    assert result.imported == 0
    assert "номер карты" in result.rejected[0].message
    assert state.transactions == []


@pytest.mark.parametrize("merchant", ["Такси 12.09 до дома", "Кофейня №5", "Чек 123456789012"])
def test_ordinary_digits_are_fine(merchant):
    _, result = apply_import(UserState(), [_row(merchant=merchant)], AS_OF)
    assert result.imported == 1


def test_future_date_rejected_today_accepted():
    rows = [_row(date=AS_OF), _row(date=AS_OF + dt.timedelta(days=1), merchant="Кафе")]
    _, result = apply_import(UserState(), rows, AS_OF)

    assert result.imported == 1
    assert [r.row for r in result.rejected] == [2]
    assert "будущем" in result.rejected[0].message


def test_empty_merchant_and_huge_amount_rejected():
    rows = [_row(merchant="   "), _row(amount="-99999999999", merchant="Ошибка")]
    _, result = apply_import(UserState(), rows, AS_OF)

    assert result.imported == 0
    assert [r.message for r in result.rejected] == [
        "Не указано описание операции.",
        "Сумма слишком большая — проверьте, нет ли лишних цифр.",
    ]


def test_unknown_category_becomes_other_with_warning():
    state, result = apply_import(UserState(), [_row(category="Кафе")], AS_OF)

    assert result.imported == 1
    assert state.transactions[0].category == "other"
    assert result.warnings == ["Строка 1: неизвестная категория «Кафе» заменена на «другое»."]


def test_duplicates_are_skipped_within_file_and_against_existing():
    demo = load_demo_state()  # уже есть «Супермаркет» −1 890 ₽ 15.09
    rows = [
        _row(amount="-1890", merchant="супермаркет ", date=dt.date(2026, 9, 15)),
        _row(amount="-300", merchant="Кофейня"),
        _row(amount="-300.00", merchant="КОФЕЙНЯ"),
    ]
    state, result = apply_import(demo, rows, DEMO_AS_OF)

    assert result.imported == 1
    assert result.warnings == [
        "Строка 1: такая операция уже есть, пропущена.",
        "Строка 3: такая операция уже есть, пропущена.",
    ]
    assert len(state.transactions) == len(demo.transactions) + 1


def test_nothing_new_warns():
    demo = load_demo_state()
    _, result = apply_import(demo, [], DEMO_AS_OF)

    assert result.imported == 0
    assert result.warnings == ["Новых операций нет."]


def test_amount_rounded_to_kopecks():
    state, _ = apply_import(UserState(), [_row(amount="-100.005")], AS_OF)
    assert state.transactions[0].amount == Decimal("-100.01")


def test_input_state_not_mutated():
    demo = load_demo_state()
    before = demo.model_copy(deep=True)
    apply_import(demo, [_row(merchant="Новая трата")], DEMO_AS_OF)

    assert demo == before


def test_same_row_gets_same_id():
    first, _ = apply_import(UserState(), [_row()], AS_OF)
    second, _ = apply_import(UserState(), [_row()], AS_OF)
    assert first.transactions[0].id == second.transactions[0].id


def test_mark_recurring_runs_after_import():
    """Абонемент в двух месяцах с одинаковой суммой становится регулярным, разовые траты — нет."""
    rows = [
        _row(amount="-1500", merchant="Спортзал", category="health", date=dt.date(2026, 8, 3)),
        _row(amount="-1500", merchant="Спортзал", category="health", date=dt.date(2026, 9, 3)),
        _row(amount="-700", merchant="Книжный", category="education"),
    ]
    state, result = apply_import(UserState(), rows, AS_OF)

    assert result.imported == 3
    assert {op.merchant: op.is_recurring for op in state.transactions} == {"Спортзал": True, "Книжный": False}


def test_demo_runway_unchanged_after_import():
    """В ветке front любой импорт делал «Супермаркет» и «Доставку еды» обязательными платежами."""
    demo = load_demo_state()
    state, _ = apply_import(demo, [_row(amount="-250", merchant="Кофейня")], DEMO_AS_OF)

    before = build_runway(demo, DEMO_AS_OF).result
    after = build_runway(state, DEMO_AS_OF).result
    assert after["days"] == before["days"]
    assert after["todaySafeSpend"] == before["todaySafeSpend"] == Decimal("475")
