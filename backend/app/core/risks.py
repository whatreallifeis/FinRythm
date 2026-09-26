"""Финансовые риски. Заглушка S1."""

from __future__ import annotations

import datetime as dt

from app.models import Profile, RiskReport


def detect_risks(profile: Profile, today: dt.date | None = None) -> RiskReport:
    return RiskReport(risks=[])
