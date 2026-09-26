"""Инструменты для LLM: схемы из contracts/tools.schema.json и выполнение вызовов поверх app.core.

dispatch() никогда не бросает исключение из-за аргументов модели: возвращает {"error": "..."},
чтобы модель увидела ошибку и исправилась. Результат — JSON-совместимый dict, деньги — строками.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from decimal import Decimal, InvalidOperation
from functools import cache
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from app.core import (
    build_snapshot,
    calculate_runway,
    detect_risks,
    plan_goal,
    simulate,
    spending_breakdown,
)
from app.models import Profile

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts" / "tools.schema.json"
EXPECTED_INCOME_K = Decimal("0.5")


class KnowledgeSearch(Protocol):
    def search(self, query: str, k: int = 3) -> list[Any]: ...


class ToolArgumentError(ValueError):
    """Неверные аргументы от модели. Текст — по-русски, для модели и логов."""


# ---------------------------------------------------------------- схемы


@cache
def tool_schemas() -> tuple[dict, ...]:
    """Инструменты из контракта: [{"name", "description", "parameters"}, ...]."""
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return tuple(data["tools"])


def tool_names() -> list[str]:
    return [t["name"] for t in tool_schemas()]


def openai_tools() -> list[dict]:
    """Схемы в формате function calling OpenAI-совместимых API."""
    return [
        {
            "type": "function",
            "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]},
        }
        for t in tool_schemas()
    ]


def _properties(name: str) -> dict:
    return next(t for t in tool_schemas() if t["name"] == name)["parameters"].get("properties", {})


# ---------------------------------------------------------------- разбор аргументов


def _check_unknown(name: str, args: dict) -> None:
    unknown = sorted(set(args) - set(_properties(name)))
    if unknown:
        allowed = ", ".join(_properties(name)) or "нет"
        raise ToolArgumentError(
            f"Инструмент {name} не принимает аргументы: {', '.join(unknown)}. Допустимые: {allowed}."
        )


def _money(args: dict, key: str, *, positive: bool = False) -> Decimal | None:
    value = args.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or (isinstance(value, float) and not math.isfinite(value)):
        raise ToolArgumentError(f"{key} должно быть числом в рублях, получено {value!r}.")
    try:
        amount = Decimal(str(value).replace(" ", "").replace(",", "."))
    except InvalidOperation:
        raise ToolArgumentError(f"{key} должно быть числом в рублях, получено {value!r}.") from None
    if not amount.is_finite():
        raise ToolArgumentError(f"{key} должно быть числом в рублях, получено {value!r}.")
    if positive and amount <= 0:
        raise ToolArgumentError(f"{key} должно быть больше нуля.")
    if amount < 0:
        raise ToolArgumentError(f"{key} не может быть отрицательным.")
    return amount.quantize(Decimal("0.01"))


def _int(args: dict, key: str, *, default: int, lo: int, hi: int) -> int:
    value = args.get(key, default)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolArgumentError(f"{key} должно быть целым числом, получено {value!r}.")
    if not lo <= value <= hi:
        raise ToolArgumentError(f"{key} должно быть от {lo} до {hi}, получено {value}.")
    return value


def _date(args: dict, key: str) -> dt.date | None:
    value = args.get(key)
    if value is None:
        return None
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        raise ToolArgumentError(
            f"{key} должно быть датой в формате ГГГГ-ММ-ДД, получено {value!r}."
        ) from None


def _dump(result: Any) -> Any:
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    if isinstance(result, dict):
        return {k: _dump(v) for k, v in result.items()}
    if isinstance(result, list | tuple):
        return [_dump(v) for v in result]
    if isinstance(result, Decimal):
        return str(result)
    if isinstance(result, dt.date):
        return result.isoformat()
    return result


# ---------------------------------------------------------------- инструменты


def _get_snapshot(args: dict, profile: Profile, kb: KnowledgeSearch | None) -> Any:
    return build_snapshot(profile)


def _calculate_runway(args: dict, profile: Profile, kb: KnowledgeSearch | None) -> Any:
    count = args.get("count_expected_income", False)
    if not isinstance(count, bool):
        raise ToolArgumentError("count_expected_income должно быть true или false.")
    return calculate_runway(profile, k=EXPECTED_INCOME_K if count else None)


def _simulate(args: dict, profile: Profile, kb: KnowledgeSearch | None) -> Any:
    purchase = _money(args, "purchase") or Decimal(0)
    delay_days = _int(args, "delay_days", default=0, lo=0, hi=60)
    if purchase == 0 and delay_days == 0:
        raise ToolArgumentError("Укажи purchase (сумму покупки) и/или delay_days (дни задержки поступления).")
    return simulate(profile, purchase=purchase, delay_days=delay_days)


def _plan_goal(args: dict, profile: Profile, kb: KnowledgeSearch | None) -> Any:
    goal_id = args.get("goal_id")
    target = _money(args, "target_amount", positive=True)
    deadline = _date(args, "deadline")
    saved = _money(args, "saved_amount")
    title = args.get("title")

    goal = None
    if goal_id is not None:
        goal = next((g for g in profile.goals if g.id == goal_id), None)
        if goal is None:
            known = ", ".join(f"{g.id} ({g.title})" for g in profile.goals) or "целей нет"
            raise ToolArgumentError(f"Цель {goal_id!r} не найдена. Цели пользователя: {known}.")
    elif target is None and deadline is None and profile.goals:
        goal = profile.goals[0]

    if goal is not None:
        return plan_goal(
            profile,
            target_amount=target or goal.target_amount,
            deadline=deadline or goal.deadline,
            saved_amount=goal.saved_amount if saved is None else saved,
            title=title or goal.title,
            goal_id=goal.id,
        )
    if target is None or deadline is None:
        hint = "Для новой цели укажи target_amount (сумму) и deadline (срок, ГГГГ-ММ-ДД)."
        if profile.goals:
            hint += " Или goal_id существующей цели: " + ", ".join(
                f"{g.id} ({g.title})" for g in profile.goals
            )
        raise ToolArgumentError(hint)
    return plan_goal(
        profile,
        target_amount=target,
        deadline=deadline,
        saved_amount=saved or Decimal(0),
        title=title or "Цель",
    )


def _spending_breakdown(args: dict, profile: Profile, kb: KnowledgeSearch | None) -> Any:
    period_days = _int(args, "period_days", default=30, lo=7, hi=180)
    result = spending_breakdown(profile, period_days=period_days)
    if result is None:
        raise ToolArgumentError(
            f"За последние {period_days} дней нет операций — структуру трат не посчитать. "
            "Пользователь может добавить операции или загрузить CSV."
        )
    return result


def _detect_risks(args: dict, profile: Profile, kb: KnowledgeSearch | None) -> Any:
    return detect_risks(profile)


def _fragment(item: Any) -> dict:
    if isinstance(item, BaseModel):
        return item.model_dump(mode="json")
    if isinstance(item, dict):
        return _dump(item)
    return _dump(vars(item))


def _search_knowledge(args: dict, profile: Profile, kb: KnowledgeSearch | None) -> Any:
    query = args.get("query")
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 200:
        raise ToolArgumentError("query — обязательная строка от 2 до 200 символов.")
    results = kb.search(query.strip(), k=3) if kb is not None else []
    return {"query": query.strip(), "results": [_fragment(r) for r in results]}


_HANDLERS = {
    "get_snapshot": _get_snapshot,
    "calculate_runway": _calculate_runway,
    "simulate": _simulate,
    "plan_goal": _plan_goal,
    "spending_breakdown": _spending_breakdown,
    "detect_risks": _detect_risks,
    "search_knowledge": _search_knowledge,
}


def dispatch(name: str, args: dict | None, profile: Profile, *, kb: KnowledgeSearch | None = None) -> dict:
    """Выполнить инструмент name с аргументами модели на профиле пользователя."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Неизвестный инструмент {name!r}. Доступные: {', '.join(tool_names())}."}
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return {"error": "Аргументы инструмента должны быть JSON-объектом."}
    try:
        _check_unknown(name, args)
        return _dump(handler(args, profile, kb))
    except ToolArgumentError as exc:
        return {"error": str(exc)}
    except ValidationError as exc:
        return {"error": f"Неверные аргументы: {exc.errors()[0].get('msg', 'ошибка проверки')}."}
