"""План накопления на цель по docs/01_project_spec.md §6.2."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.core.money import ceil_rub, to_money
from app.core.runway import _as_of
from app.models import GoalPlan, Profile

ZERO = Decimal(0)


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
    target, saved = Decimal(target_amount), Decimal(saved_amount)
    goal = next((g for g in profile.goals if g.id == goal_id), None) if goal_id else None
    current_daily = goal.daily_contribution if goal else ZERO

    days_left = (deadline - as_of).days
    need = target - saved

    if need <= 0:
        required, projected = ZERO, as_of
    else:
        # Срок прошёл или сегодня — вся недостающая сумма нужна сразу.
        required = ceil_rub(need / days_left) if days_left > 0 else ceil_rub(need)
        projected = (
            as_of + dt.timedelta(days=int(ceil_rub(need / current_daily))) if current_daily > 0 else None
        )

    by_deadline = saved + current_daily * max(0, days_left)
    return GoalPlan(
        goal_id=goal_id,
        title=title,
        target_amount=to_money(target),
        saved_amount=to_money(saved),
        deadline=deadline,
        days_left=days_left,
        required_daily=required,
        current_daily=to_money(current_daily),
        amount_by_deadline=to_money(by_deadline),
        projected_date=projected,
        on_track=need <= 0 or by_deadline >= target,
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
