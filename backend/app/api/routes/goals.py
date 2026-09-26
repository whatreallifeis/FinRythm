"""Цели накопления: создание, правка, удаление и план (план считает core)."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api import engine
from app.api.deps import current_session, get_store, get_today
from app.api.schemas import GoalIn
from app.api.serialize import public_explained, public_goal
from app.models import SavingGoal
from app.storage import Session, Store

router = APIRouter(prefix="/goals")

NOT_FOUND = "Цель не найдена."


def _goal(goal_id: str, body: GoalIn) -> SavingGoal:
    return SavingGoal(
        id=goal_id,
        title=body.title.strip(),
        target_amount=body.target_amount,
        saved_amount=body.saved_amount,
        deadline=body.deadline,
    )


@router.post("", status_code=201)
def create_goal(
    body: GoalIn, session: Session = Depends(current_session), store: Store = Depends(get_store)
) -> dict:
    state = store.load(session.user_id)
    goal = _goal(f"g-{uuid.uuid4().hex[:8]}", body)
    state.goals.append(goal)
    store.save(session.user_id, state)
    return public_goal(goal)


@router.patch("/{goal_id}")
def update_goal(
    goal_id: str, body: GoalIn, session: Session = Depends(current_session), store: Store = Depends(get_store)
) -> dict:
    state = store.load(session.user_id)
    for index, goal in enumerate(state.goals):
        if goal.id == goal_id:
            state.goals[index] = _goal(goal_id, body)
            store.save(session.user_id, state)
            return public_goal(state.goals[index])
    raise HTTPException(status_code=404, detail=NOT_FOUND)


@router.delete("/{goal_id}", status_code=204)
def delete_goal(
    goal_id: str, session: Session = Depends(current_session), store: Store = Depends(get_store)
) -> Response:
    state = store.load(session.user_id)
    remaining = [goal for goal in state.goals if goal.id != goal_id]
    if len(remaining) == len(state.goals):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    state.goals = remaining
    store.save(session.user_id, state)
    return Response(status_code=204)


@router.get("/{goal_id}/plan")
def goal_plan(
    goal_id: str,
    session: Session = Depends(current_session),
    store: Store = Depends(get_store),
    today: date = Depends(get_today),
) -> dict:
    state = store.load(session.user_id)
    if not any(goal.id == goal_id for goal in state.goals):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    plan = engine.build_goal_plan(state, goal_id, today)
    if plan is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return public_explained(plan)
