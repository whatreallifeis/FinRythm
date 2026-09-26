"""Тела запросов фронтенда (camelCase). Ответы собирает app.api.serialize."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


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
