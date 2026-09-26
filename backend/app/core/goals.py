"""План накопления на цель. Заглушка S1."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.core.runway import _as_of
from app.models import GoalPlan, Profile


def plan_goal(
    profile: Profile,
    *,
    target_amount: Decimal,
    deadline: dt.date,
    saved_amount: Decimal = Decimal(0),
    title: str = "Цель",
    goal_id: str | None = None,
    today: dt.date | None = None,
) -> GoalPlan:
    as_of = _as_of(profile, today)
    return GoalPlan(
        goal_id=goal_id,
        title=title,
        target_amount=target_amount,
        saved_amount=saved_amount,
        deadline=deadline,
        days_left=(deadline - as_of).days,
        required_daily=Decimal(0),
        current_daily=Decimal(0),
        amount_by_deadline=saved_amount,
        projected_date=None,
        on_track=saved_amount >= target_amount,
    )


def plan_all_goals(profile: Profile, today: dt.date | None = None) -> list[GoalPlan]:
    return [
        plan_goal(
            profile,
            target_amount=g.target_amount,
            deadline=g.deadline,
            saved_amount=g.saved_amount,
            title=g.title,
            goal_id=g.id,
            today=today,
        )
        for g in profile.goals
    ]
