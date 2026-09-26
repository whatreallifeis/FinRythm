"""Тела запросов фронтенда (camelCase). Ответы собирает app.api.serialize."""

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from app.models import ScenarioId


class _In(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class IncomeIn(_In):
    id: str | None = None
    title: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    day_of_month: int = Field(ge=1, le=31)


class ProfileIn(_In):
    balance: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    incomes: list[IncomeIn] = Field(default_factory=list, max_length=20)


class TelegramIn(_In):
    init_data: str = Field(min_length=1)


class GoalIn(_In):
    title: str = Field(min_length=1, max_length=100)
    target_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    saved_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    deadline: date | None = None

    @model_validator(mode="after")
    def _saved_not_above_target(self) -> "GoalIn":
        if self.saved_amount > self.target_amount:
            raise ValueError("Накоплено не может быть больше суммы цели")
        return self


class ImpulseIn(_In):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class ImportRowIn(_In):
    """Строка импорта от фронтенда. Дата — строкой: её проверяет API построчно, чтобы одна
    несуществующая дата (2026-02-30) не отклоняла весь файл (#52)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    date: str = Field(max_length=40)
    amount: Decimal
    category: str = "other"
    merchant: str = ""
    row: int | None = Field(default=None, ge=1)  # номер строки в файле (#36)


class ImportIn(_In):
    rows: list[ImportRowIn] = Field(max_length=5000)


class AskIn(_In):
    question: str = Field(min_length=1, max_length=1000)
    scenario_id: ScenarioId


class HistoryEntryIn(_In):
    """Сохранённый диалог. Сервер хранит его как прислал фронтенд, проверяя только каркас."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="allow")

    id: str = Field(min_length=1, max_length=100)
    scenario_id: ScenarioId
    title: str = Field(max_length=300)
    created_at: str = Field(min_length=1, max_length=40)
    messages: list[dict[str, Any]] = Field(max_length=200)
