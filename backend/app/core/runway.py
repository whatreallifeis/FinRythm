"""Дневной лимит и «что если». Заглушка S1: возвращает эталон P1."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.models import Profile, RunwayResult, SimulationResult


def _as_of(profile: Profile, today: dt.date | None) -> dt.date:
    return today or profile.as_of or dt.date.today()


def calculate_runway(
    profile: Profile,
    *,
    purchase: Decimal = Decimal(0),
    delay_days: int = 0,
    k: Decimal | None = None,
    today: dt.date | None = None,
) -> RunwayResult:
    return RunwayResult(
        status="ok",
        as_of=_as_of(profile, today),
        next_income_date=dt.date(2026, 10, 10),
        next_income_title="Стипендия",
        horizon_days=14,
        balance=Decimal("9800.00"),
        mandatory_total=Decimal("1949.00"),
        free=Decimal("7851.00"),
        reserve=Decimal("785.10"),
        goal_contribution=Decimal("1400.00"),
        expected_income_counted=Decimal("0.00"),
        available=Decimal("5665.90"),
        daily_limit=Decimal("404"),
        deficit=Decimal("0.00"),
        formula_text="(9 800 − 1 949 обяз. − 785,10 резерв − 1 400 в цель) ÷ 14 дн. = 404 ₽ в день",
    )


def simulate(
    profile: Profile,
    *,
    purchase: Decimal = Decimal(0),
    delay_days: int = 0,
    today: dt.date | None = None,
) -> SimulationResult:
    before = calculate_runway(profile, today=today)
    after = calculate_runway(profile, purchase=purchase, delay_days=delay_days, today=today)
    return SimulationResult(
        purchase=purchase,
        delay_days=delay_days,
        before=before,
        after=after,
        delta_daily_limit=after.daily_limit - before.daily_limit,
    )
