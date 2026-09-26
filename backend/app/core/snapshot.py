"""Сводка профиля для инструмента get_snapshot. Заглушка S1."""

from __future__ import annotations

import datetime as dt

from app.core.runway import _as_of
from app.models import Profile


def build_snapshot(profile: Profile, today: dt.date | None = None) -> dict:
    return {
        "as_of": _as_of(profile, today).isoformat(),
        "balance": None if profile.balance is None else str(profile.balance),
        "next_confirmed_income": None,
        "expected_incomes": [],
        "payments_next_30_days": [],
        "goals": [],
        "missing": [],
    }
