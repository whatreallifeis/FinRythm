"""Мост API к core (Саша), ingest (Саша) и ai (Соня).

Функции ищутся по имени при каждом вызове: пока их нет в main, работает заглушка из app.api.stubs,
а после мержа — настоящий расчёт, без правок в API.
"""

import inspect
from datetime import date
from decimal import Decimal

import app.ai as ai
import app.core as core
import app.ingest as ingest
from app.api import stubs
from app.models import Explained, ImportResult, ImportRow, UserState


def _impl(module, name: str):
    return getattr(module, name, None) or getattr(stubs, name)


def build_overview(state: UserState, as_of: date) -> Explained:
    return _impl(core, "build_overview")(state, as_of)


def build_forecast(state: UserState, as_of: date) -> Explained:
    return _impl(core, "build_forecast")(state, as_of)


def build_runway(state: UserState, as_of: date) -> Explained:
    return _impl(core, "build_runway")(state, as_of)


def check_impulse(state: UserState, amount: Decimal, as_of: date) -> Explained:
    return _impl(core, "check_impulse")(state, amount, as_of)


def build_goal_plan(state: UserState, goal_id: str, as_of: date) -> Explained | None:
    return _impl(core, "build_goal_plan")(state, goal_id, as_of)


def load_demo_state() -> UserState:
    return core.load_demo_state()


def apply_import(state: UserState, rows: list[ImportRow], as_of: date) -> tuple[UserState, ImportResult]:
    return _impl(ingest, "apply_import")(state, rows, as_of)


async def ask(question: str, scenario_id: str, state: UserState, as_of: date, *, llm, kb) -> Explained:
    result = _impl(ai, "ask")(question, scenario_id, state, as_of, llm=llm, kb=kb)
    if inspect.isawaitable(result):
        result = await result
    return result


def llm_errors() -> tuple[type[BaseException], ...]:
    """Ошибки провайдера LLM, которые API превращает в 503 (класс LLMUnavailable у Сони)."""
    error = getattr(ai, "LLMUnavailable", None)
    return (error,) if isinstance(error, type) else ()


def load_kb(path: str):
    """База знаний Сони; пока её нет — None (помощник ответит без источников)."""
    loader = getattr(ai, "load_kb", None)
    return loader(path) if loader else None
