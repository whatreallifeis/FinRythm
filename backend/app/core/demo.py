"""Демо-профиль студента для нового API (data/demo/student.json, перенесён из demo_data.py ветки front)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from app.models import UserState

DEMO_PATH = Path(__file__).resolve().parents[3] / "data" / "demo" / "student.json"
# Дата, на которую рассчитан демо-сценарий (handoff.md ветки front).
DEMO_AS_OF = dt.date(2026, 9, 26)


def load_demo_state(path: Path | None = None) -> UserState:
    """Баланс 18 430 ₽, стипендия 8 000 ₽ 5-го, подработка 25 000 ₽ 10-го, две цели, операции за 2 месяца."""
    return UserState.model_validate_json((path or DEMO_PATH).read_text(encoding="utf-8"))
