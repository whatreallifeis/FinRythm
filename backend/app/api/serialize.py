"""Граница JSON для фронтенда: camelCase и деньги числами.

Внутри бэкенда деньги — Decimal. Во float они превращаются только здесь, с округлением до копейки,
потому что фронтенд (types.ts) ждёт number.
"""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel

from app.core.runway_calendar import Bill, bills_of
from app.models import Explained, IncomeRule, Operation, SavingGoal, UserState

CENT = Decimal("0.01")


def money(value: Decimal) -> float:
    return float(value.quantize(CENT, ROUND_HALF_UP))


def to_json(value: Any) -> Any:
    """Decimal → число, дата → ГГГГ-ММ-ДД, рекурсивно по словарям и спискам."""
    if isinstance(value, bool) or value is None or isinstance(value, int | float | str):
        return value
    if isinstance(value, Decimal):
        # Не округляем: core уже отдаёт деньги с точностью до копейки, а доли — до 4 знаков (issue #24).
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return to_json(value.model_dump())
    if isinstance(value, dict):
        return {str(key): to_json(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_json(item) for item in value]
    raise TypeError(f"Не умею отдать в JSON: {type(value).__name__}")


def public_operation(op: Operation) -> dict:
    return {
        "id": op.id,
        "date": op.date.isoformat(),
        "amount": money(op.amount),
        "category": op.category,
        "merchant": op.merchant,
        "isRecurring": op.is_recurring,
    }


def public_income(income: IncomeRule) -> dict:
    return {
        "id": income.id,
        "title": income.title,
        "amount": money(income.amount),
        "dayOfMonth": income.day_of_month,
    }


def public_autopayment(bill: Bill) -> dict:
    """Автоплатёж календаря: найденный в выписке (id «rec-…») или добавленный вручную."""
    return {
        "id": bill.id,
        "title": bill.title,
        "amount": money(bill.amount),
        "dayOfMonth": bill.day,
        "category": bill.category,
    }


def public_goal(goal: SavingGoal) -> dict:
    return {
        "id": goal.id,
        "title": goal.title,
        "targetAmount": money(goal.target_amount),
        "savedAmount": money(goal.saved_amount),
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
    }


def public_profile(state: UserState) -> dict:
    return {
        # Фронтенд ждёт число; «баланс не указан» он узнаёт из dataQuality аналитики.
        "balance": money(state.balance) if state.balance is not None else 0,
        "incomes": [public_income(item) for item in state.incomes],
        "autopayments": [
            public_autopayment(bill) for bill in sorted(bills_of(state), key=lambda b: (b.day, b.title))
        ],
        "goals": [public_goal(item) for item in state.goals],
    }


def public_transactions(state: UserState) -> list[dict]:
    rows = sorted(state.transactions, key=lambda op: (op.date, op.id), reverse=True)
    return [public_operation(op) for op in rows]


def public_explained(payload: Explained) -> dict:
    return {
        "result": to_json(payload.result),
        "assumptions": list(payload.assumptions),
        "calculation": [
            {"label": step.label, "formula": step.formula, "value": float(step.value)}
            for step in payload.calculation
        ],
        "sources": [{"title": source.title, "url": source.url} for source in payload.sources],
        "limitations": list(payload.limitations),
        "dataQuality": {
            "sufficient": payload.data_quality.sufficient,
            "missing": list(payload.data_quality.missing),
            "coverageDays": payload.data_quality.coverage_days,
        },
    }
