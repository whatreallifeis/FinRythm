"""
ОБЩИЙ КОНТРАКТ ПРОЕКТА «ФинРитм».

Этот файл — единственный источник правды о структуре данных для всех модулей:
core (Саша), ai (Соня), api/storage (Вероника), ingest (Саша), e2e (Саша).

Правила изменения:
  * Менять только через PR с меткой `contract`.
  * Перед мержем — issue to:veronika со ссылкой на PR (ревью не требуется, см. CLAUDE.md).
  * Добавлять поля можно (с default), удалять и переименовывать — только по согласованию всех.

Деньги — всегда Decimal. float для денег запрещён.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


# ---------------------------------------------------------------- входные данные


class IncomeType(StrEnum):
    stipend = "stipend"  # стипендия
    job = "job"  # подработка / фриланс
    family = "family"  # помощь семьи
    other = "other"


class Income(_Model):
    """Будущее поступление денег."""

    id: str
    title: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    date: dt.date
    type: IncomeType
    confirmed: bool = Field(
        description="True — дата и сумма известны (стипендия). False — ожидаемые деньги (подработка)."
    )


class Period(StrEnum):
    once = "once"
    weekly = "weekly"
    monthly = "monthly"


class MandatoryPayment(_Model):
    """Обязательный платёж: аренда, связь, проезд, подписка."""

    id: str
    title: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    next_date: dt.date
    period: Period = Period.monthly
    category: str = "Другое"


class Goal(_Model):
    id: str
    title: str = Field(min_length=1, max_length=100)
    target_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    deadline: dt.date
    saved_amount: Decimal = Field(default=Decimal("0"), ge=0)
    daily_contribution: Decimal = Field(default=Decimal("0"), ge=0)


class Transaction(_Model):
    """Операция. amount < 0 — расход, amount > 0 — доход."""

    id: str
    date: dt.date
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    description: str = Field(min_length=1, max_length=200)
    category: str | None = None
    source: Literal["manual", "csv", "demo"] = "manual"


class Settings(_Model):
    reserve_pct: Decimal = Field(default=Decimal("10"), ge=0, le=50)
    expected_income_k: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    default_horizon_days: int = Field(default=30, ge=1, le=90)


class DataOrigin(_Model):
    kind: Literal["demo", "manual", "csv"]
    label: str  # «Синтетический профиль P1, сгенерирован 26.09.2026»
    updated_at: dt.datetime


class Profile(_Model):
    """Все данные одного пользователя. Хранится в SQLite целиком (JSON)."""

    as_of: dt.date | None = Field(
        default=None, description="Дата расчёта. None → сегодня. В демо-профилях зафиксирована."
    )
    balance: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    incomes: list[Income] = Field(default_factory=list)
    payments: list[MandatoryPayment] = Field(default_factory=list)
    goals: list[Goal] = Field(default_factory=list)
    transactions: list[Transaction] = Field(default_factory=list)
    settings: Settings = Field(default_factory=Settings)
    origin: DataOrigin | None = None


# ---------------------------------------------------------------- результаты core


class Assumption(_Model):
    code: str  # horizon_default | income_today | expected_income_counted | goal_paused | ...
    text: str  # человекочитаемо, по-русски


class MissingData(_Model):
    field: str  # balance | payments | incomes | transactions | goals
    message: str  # «Укажите текущий баланс, без него лимит не посчитать»


class PaymentOccurrence(_Model):
    title: str
    amount: Decimal
    date: dt.date


class RunwayResult(_Model):
    status: Literal["ok", "deficit", "insufficient_data"]
    as_of: dt.date
    next_income_date: dt.date | None = None
    next_income_title: str | None = None
    horizon_days: int = 0
    horizon_is_assumed: bool = False
    balance: Decimal = Decimal("0")
    mandatory_total: Decimal = Decimal("0")
    mandatory_items: list[PaymentOccurrence] = Field(default_factory=list)
    free: Decimal = Decimal("0")
    reserve: Decimal = Decimal("0")
    goal_contribution: Decimal = Decimal("0")
    expected_income_counted: Decimal = Decimal("0")
    available: Decimal = Decimal("0")
    daily_limit: Decimal = Decimal("0")
    deficit: Decimal = Decimal("0")
    formula_text: str = ""  # формула с подставленными числами для показа пользователю
    assumptions: list[Assumption] = Field(default_factory=list)
    missing: list[MissingData] = Field(default_factory=list)


class SimulationResult(_Model):
    purchase: Decimal = Decimal("0")
    delay_days: int = 0
    before: RunwayResult
    after: RunwayResult
    delta_daily_limit: Decimal


class GoalPlan(_Model):
    goal_id: str | None = None
    title: str
    target_amount: Decimal
    saved_amount: Decimal
    deadline: dt.date
    days_left: int
    required_daily: Decimal  # нужно откладывать в день, чтобы успеть (округление вверх до рубля)
    current_daily: Decimal  # сейчас откладывается в день
    amount_by_deadline: Decimal  # сколько будет к сроку при текущем темпе
    projected_date: dt.date | None  # когда цель будет достигнута при текущем темпе (None, если темп 0)
    on_track: bool


class CategoryStat(_Model):
    category: str
    total: Decimal  # положительное число (сумма расходов)
    share_pct: Decimal  # 0..100, 1 знак после запятой; сумма по категориям = 100.0 (±0.1)
    count: int


class RecurringItem(_Model):
    description: str
    amount: Decimal
    interval_days: int
    occurrences: int
    monthly_cost: Decimal
    is_subscription: bool


class Breakdown(_Model):
    period_from: dt.date
    period_to: dt.date
    total_expenses: Decimal
    total_income: Decimal
    categories: list[CategoryStat]
    recurring: list[RecurringItem]
    large: list[Transaction]


class Risk(_Model):
    kind: Literal["subscription", "anomaly", "zero_balance", "deficit", "no_data"]
    severity: Literal["info", "warning", "critical"]
    title: str
    details: str
    amount: Decimal | None = None
    date: dt.date | None = None


class RiskReport(_Model):
    risks: list[Risk]
    balance_zero_date: dt.date | None = None


class ImportRowError(_Model):
    row: int  # номер строки CSV, начиная с 2 (1 — заголовок)
    field: str | None
    message: str


class ImportReport(_Model):
    added: int
    skipped: int
    duplicates: int
    errors: list[ImportRowError]
    mode: Literal["append", "replace"]


# ---------------------------------------------------------------- AI / чат


class ChatRequest(_Model):
    message: str = Field(min_length=1, max_length=1000)


class ToolCallInfo(_Model):
    name: str
    arguments: dict[str, Any]
    ok: bool
    error: str | None = None


class Source(_Model):
    title: str
    url: str
    checked_at: dt.date


class AnswerBlocks(_Model):
    result: str  # главный ответ, 1–3 предложения
    basis: str  # на каких данных основано
    assumptions: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class ChatResponse(_Model):
    answer: str  # полный текст ответа (для бота)
    blocks: AnswerBlocks | None = None  # структура (для фронтенда); None при отказе
    tool_calls: list[ToolCallInfo] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    refused: bool = False
    # investment | crypto | credit | gambling | money_transfer | decide_for_me | personal_data | out_of_scope
    refusal_reason: str | None = None
    number_check_passed: bool = True
    disclaimer: str = "Не является финансовой рекомендацией. AI может ошибаться — проверяйте важные данные."


# ---------------------------------------------------------------- API


class ApiError(_Model):
    code: str  # validation_error | not_found | insufficient_data | llm_unavailable | internal
    message: str  # по-русски, для пользователя
    field: str | None = None
    row: int | None = None


class ErrorResponse(_Model):
    error: ApiError


class SummaryResponse(_Model):
    """Всё для дашборда одним запросом."""

    runway: RunwayResult
    breakdown: Breakdown | None
    risks: RiskReport
    goals: list[GoalPlan]
    origin: DataOrigin | None


class SimulateRequest(_Model):
    purchase: Decimal = Field(default=Decimal("0"), ge=0)
    delay_days: int = Field(default=0, ge=0, le=60)


class GoalPlanRequest(_Model):
    title: str = "Цель"
    target_amount: Decimal = Field(gt=0)
    deadline: dt.date
    saved_amount: Decimal = Field(default=Decimal("0"), ge=0)


class SessionResponse(_Model):
    user_id: str


class TelegramAuthRequest(_Model):
    init_data: str


# ================================================================ модели фронтенда
#
# Фронтенд ruina696 (ветка `front`, frontend/src/shared/api/types.ts) ждёт другие формы данных,
# чем модели выше. Её указания по бэкенду в приоритете (см. CLAUDE.md), поэтому новый API
# строится на моделях этого раздела. Старые модели не удаляются: на них работают core и ai.
#
# Внутри деньги — Decimal, поля — snake_case. В JSON для фронтенда API переводит поля в camelCase,
# а деньги в числа — только на границе HTTP (backend/app/api/).

CategoryId = Literal[
    "food", "transport", "subscriptions", "entertainment", "health", "education", "rent", "other"
]
CATEGORY_IDS: tuple[str, ...] = get_args(CategoryId)

ScenarioId = Literal["expenses", "budget", "glossary", "impulse", "free"]
SCENARIO_IDS: tuple[str, ...] = get_args(ScenarioId)


class Operation(_Model):
    """Операция из выписки. amount < 0 — расход, amount > 0 — доход. Во фронтенде — Transaction."""

    id: str
    date: dt.date
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    category: CategoryId = "other"
    merchant: str = Field(default="", max_length=200)
    is_recurring: bool = False


class IncomeRule(_Model):
    """Регулярное поступление: стипендия, зарплата, подработка — каждый месяц в один и тот же день."""

    id: str
    title: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    day_of_month: int = Field(ge=1, le=31)


class SavingGoal(_Model):
    """Цель накопления. Во фронтенде — Goal."""

    id: str
    title: str = Field(min_length=1, max_length=100)
    target_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    saved_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    deadline: dt.date | None = None

    @model_validator(mode="after")
    def _saved_not_above_target(self) -> SavingGoal:
        if self.saved_amount > self.target_amount:
            raise ValueError("Накоплено не может быть больше суммы цели")
        return self


class UserState(_Model):
    """Все данные одного пользователя для нового API. Хранится в SQLite целиком (JSON)."""

    balance: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    incomes: list[IncomeRule] = Field(default_factory=list)
    goals: list[SavingGoal] = Field(default_factory=list)
    transactions: list[Operation] = Field(default_factory=list)
    # Сохранённые диалоги помощника (HistoryEntry фронтенда). API хранит их как есть, core их не читает.
    history: list[dict[str, Any]] = Field(default_factory=list)


class ImportRow(_Model):
    """Строка импорта. CSV разбирает фронтенд и присылает строки JSON-ом."""

    date: dt.date
    amount: Decimal
    category: str = "other"  # неизвестная категория → "other" с предупреждением (решает ingest)
    merchant: str = ""
    # Номер строки в исходном файле (заголовок — строка 1). Необязателен: если фронтенд его прислал,
    # API подставляет его в rejected[].row и в «Строка N: …» предупреждений вместо номера в списке.
    row: int | None = Field(default=None, ge=1)


class RejectedRow(_Model):
    row: int = Field(ge=1)  # номер строки в присланном списке, начиная с 1
    message: str  # по-русски, для пользователя


class ImportResult(_Model):
    imported: int = Field(ge=0)
    rejected: list[RejectedRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- обёртка объяснимости


class CalcStep(_Model):
    """Шаг расчёта: «Можно тратить в день» · «7 800 ₽ / 12 дней» · 650."""

    label: str
    formula: str  # человекочитаемая формула с подставленными числами
    value: Decimal


class SourceRef(_Model):
    title: str
    url: str


class DataQuality(_Model):
    sufficient: bool  # False — фронтенд показывает, чего не хватает, и не показывает result
    missing: list[str] = Field(default_factory=list)  # «текущий баланс», «операции за текущий месяц»
    coverage_days: int = Field(default=0, ge=0)  # за сколько дней есть операции


class Explained(_Model):
    """Каждый аналитический ответ нового API (Explained<T> во фронтенде).

    result — словарь с ключами ровно как в types.ts (camelCase: todaySafeSpend, redDays, ...),
    деньги в нём — Decimal. При data_quality.sufficient = False result может быть «пустым» ответом
    нужной формы (нули и пустые списки).
    """

    result: dict[str, Any]
    assumptions: list[str] = Field(default_factory=list)
    calculation: list[CalcStep] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    data_quality: DataQuality
