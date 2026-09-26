"""Финансовое ядро: все расчёты денег. Чистые функции, только Decimal."""

from app.core.breakdown import spending_breakdown
from app.core.categories import categorize
from app.core.demo import DEMO_AS_OF, load_demo_state
from app.core.goals import plan_all_goals, plan_goal
from app.core.recurring import detect_recurring
from app.core.risks import detect_risks
from app.core.runway import calculate_runway, simulate
from app.core.snapshot import build_snapshot

__all__ = [
    "DEMO_AS_OF",
    "build_snapshot",
    "calculate_runway",
    "categorize",
    "detect_recurring",
    "detect_risks",
    "load_demo_state",
    "plan_all_goals",
    "plan_goal",
    "simulate",
    "spending_breakdown",
]
