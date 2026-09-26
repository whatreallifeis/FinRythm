"""Данные пользователя: профиль, операции, очистка набора."""

import uuid

from fastapi import APIRouter, Depends, Response

from app.api.deps import current_session, get_store
from app.api.schemas import ProfileIn
from app.api.serialize import public_profile, public_transactions
from app.models import IncomeRule
from app.storage import Session, Store

router = APIRouter()


@router.get("/profile")
def read_profile(session: Session = Depends(current_session), store: Store = Depends(get_store)) -> dict:
    return public_profile(store.load(session.user_id))


@router.put("/profile")
def write_profile(
    body: ProfileIn, session: Session = Depends(current_session), store: Store = Depends(get_store)
) -> dict:
    state = store.load(session.user_id)
    state.balance = body.balance
    state.incomes = [
        IncomeRule(
            id=item.id or f"i-{uuid.uuid4().hex[:8]}",
            title=item.title.strip(),
            amount=item.amount,
            day_of_month=item.day_of_month,
        )
        for item in body.incomes
    ]
    store.save(session.user_id, state)
    return public_profile(state)


@router.delete("/dataset", status_code=204)
def clear_dataset(session: Session = Depends(current_session), store: Store = Depends(get_store)) -> Response:
    store.clear(session.user_id)
    return Response(status_code=204)


@router.get("/transactions")
def list_transactions(
    session: Session = Depends(current_session), store: Store = Depends(get_store)
) -> list[dict]:
    return public_transactions(store.load(session.user_id))
