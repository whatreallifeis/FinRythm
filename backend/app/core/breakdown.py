"""Структура расходов за период. Заглушка S1."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.core.runway import _as_of
from app.models import Breakdown, Profile


def spending_breakdown(
    profile: Profile, *, period_days: int = 30, today: dt.date | None = None
) -> Breakdown | None:
    as_of = _as_of(profile, today)
    return Breakdown(
        period_from=as_of - dt.timedelta(days=period_days),
        period_to=as_of,
        total_expenses=Decimal("0.00"),
        total_income=Decimal("0.00"),
        categories=[],
        recurring=[],
        large=[],
    )
