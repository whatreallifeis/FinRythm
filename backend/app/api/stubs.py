"""Честные заглушки на время, пока расчёта нет в main.

Отвечают правильной формой (types.ts), но с data_quality.sufficient = False: фронтенд покажет,
что результата пока нет, а не выдуманные числа. Как только Саша или Соня вливают свою функцию,
app.api.engine берёт её, а заглушка перестаёт вызываться.
"""

from datetime import date
from decimal import Decimal

from app.models import DataQuality, Explained, ImportResult, ImportRow, UserState

PENDING = "расчёт ещё не подключён на сервере — попробуйте позже"
LIMITS = ["Это не финансовая рекомендация. Решение остаётся за вами."]


def _pending(result: dict) -> Explained:
    return Explained(
        result=result, limitations=LIMITS, data_quality=DataQuality(sufficient=False, missing=[PENDING])
    )


def build_overview(state: UserState, as_of: date) -> Explained:
    first = as_of.replace(day=1)
    return _pending(
        {
            "periodFrom": first,
            "periodTo": as_of,
            "totalIncome": Decimal(0),
            "totalExpense": Decimal(0),
            "recurringTotal": Decimal(0),
            "byCategory": [],
            "anomalies": [],
        }
    )


def build_forecast(state: UserState, as_of: date) -> Explained:
    return _pending(
        {
            "daysLeft": 0,
            "expectedIncome": Decimal(0),
            "plannedExpenses": Decimal(0),
            "projectedBalance": Decimal(0),
            "safeDailySpend": Decimal(0),
            "verdict": "ok",
        }
    )


def build_runway(state: UserState, as_of: date) -> Explained:
    return _pending(
        {
            "horizonTo": as_of,
            "nextIncome": None,
            "todaySafeSpend": Decimal(0),
            "lowestBalance": Decimal(0),
            "redDays": 0,
            "days": [],
        }
    )


def check_impulse(state: UserState, amount: Decimal, as_of: date) -> Explained:
    return _pending(
        {
            "amount": amount,
            "verdict": "wait",
            "hint": "Проверка покупки скоро появится.",
            "todaySafeSpendBefore": Decimal(0),
            "todaySafeSpendAfter": Decimal(0),
            "redDaysBefore": 0,
            "redDaysAfter": 0,
            "lowestBalanceAfter": Decimal(0),
            "waitUntil": None,
            "goalImpact": None,
            "daysAfter": [],
        }
    )


def build_goal_plan(state: UserState, goal_id: str, as_of: date) -> Explained | None:
    if not any(goal.id == goal_id for goal in state.goals):
        return None
    return _pending(
        {"goalId": goal_id, "monthlyPace": Decimal(0), "etaMonths": None, "etaDate": None, "blockers": []}
    )


def apply_import(state: UserState, rows: list[ImportRow], as_of: date) -> tuple[UserState, ImportResult]:
    return state, ImportResult(
        imported=0, warnings=["Импорт операций ещё не подключён на сервере. Попробуйте позже."]
    )


async def ask(question: str, scenario_id: str, state: UserState, as_of: date, *, llm, kb) -> Explained:
    return _pending({"text": "Помощник ещё не подключён на сервере. Попробуйте позже."})
