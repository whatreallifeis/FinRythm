from datetime import date
from decimal import Decimal

from app.core.calendar import build_impulse, build_runway
from app.demo_data import DEMO_INCOMES, DEMO_TRANSACTIONS


def test_runway_keeps_money_until_stipend():
    """26 сентября, баланс 18 430 ₽. До стипендии 5 октября остаются аренда и мелкие платежи."""
    runway = build_runway(Decimal("18430"), DEMO_INCOMES, DEMO_TRANSACTIONS, date(2026, 9, 26))

    assert runway["nextIncome"]["title"] == "Стипендия"
    assert runway["nextIncome"]["date"] == "2026-10-05"
    assert runway["nextIncome"]["daysUntil"] == 9
    # (18430 − 12000 − 299 − 649 − 1200) // 9 = 475
    assert runway["todaySafeSpend"] == 475
    assert runway["redDays"] == 0


def test_large_purchase_breaks_the_runway():
    check = build_impulse(
        Decimal("18430"),
        DEMO_INCOMES,
        DEMO_TRANSACTIONS,
        [
            {
                "id": "g-1",
                "title": "Ноутбук",
                "targetAmount": "75000",
                "savedAmount": "21000",
                "deadline": "2027-02-01",
            }
        ],
        date(2026, 9, 26),
        Decimal("14900"),
    )

    assert check["verdict"] == "shortfall"
    assert check["todaySafeSpendAfter"] < check["todaySafeSpendBefore"]
    assert check["lowestBalanceAfter"] < 0
    # Стипендии 8 000 ₽ не хватает закрыть дыру, хватает следующей подработки.
    assert check["waitUntil"]["title"] == "Подработка"
    assert check["goalImpact"]["goalTitle"] == "Ноутбук"
    assert check["goalImpact"]["delayDays"] >= 1
