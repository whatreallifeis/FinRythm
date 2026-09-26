"""Все вызовы расчётов app.core для сценариев помощника — в одном месте.

Функции нового API Саша добавляет в app.core в задаче SF3; договорённость о сигнатурах — issue #16.
Пока функции нет, вызов бросает CoreNotReady, и сценарий честно отвечает, что расчёт не подключён.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import app.core as core
from app.models import Explained, UserState


class CoreNotReady(RuntimeError):
    """В app.core ещё нет нужной функции."""


def _fn(name: str) -> Callable[..., Any]:
    fn = getattr(core, name, None)
    if fn is None:
        raise CoreNotReady(name)
    return fn


def runway(state: UserState, as_of: dt.date) -> Explained:
    return _fn("build_runway")(state, as_of)


def impulse(state: UserState, amount: Decimal, as_of: dt.date) -> Explained:
    return _fn("check_impulse")(state, amount, as_of)


def forecast(state: UserState, as_of: dt.date) -> Explained:
    return _fn("build_forecast")(state, as_of)


def overview(state: UserState, as_of: dt.date) -> Explained:
    return _fn("build_overview")(state, as_of)


def goal_plan(state: UserState, goal_id: str, as_of: dt.date) -> Explained | None:
    """None — цели с таким id нет."""
    return _fn("build_goal_plan")(state, goal_id, as_of)


def coverage(state: UserState, as_of: dt.date) -> int:
    """За сколько дней есть операции; 0, пока функции нет в core."""
    fn = getattr(core, "coverage_days", None)
    return int(fn(state.transactions, as_of)) if fn else 0
