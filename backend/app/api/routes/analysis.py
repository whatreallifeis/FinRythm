"""Аналитика: обзор трат, прогноз до конца месяца, календарь до поступления, проверка покупки.

Считает core (через app.api.engine). API только загружает данные и отдаёт Explained фронтенду.
"""

from datetime import date

from fastapi import APIRouter, Depends

from app.api import engine
from app.api.deps import current_session, get_store, get_today
from app.api.schemas import ImpulseIn
from app.api.serialize import public_explained
from app.storage import Session, Store

router = APIRouter(prefix="/analysis")


@router.get("/overview")
def overview(
    session: Session = Depends(current_session),
    store: Store = Depends(get_store),
    today: date = Depends(get_today),
) -> dict:
    return public_explained(engine.build_overview(store.load(session.user_id), today))


@router.get("/forecast")
def forecast(
    session: Session = Depends(current_session),
    store: Store = Depends(get_store),
    today: date = Depends(get_today),
) -> dict:
    return public_explained(engine.build_forecast(store.load(session.user_id), today))


@router.get("/runway")
def runway(
    session: Session = Depends(current_session),
    store: Store = Depends(get_store),
    today: date = Depends(get_today),
) -> dict:
    return public_explained(engine.build_runway(store.load(session.user_id), today))


@router.post("/impulse")
def impulse(
    body: ImpulseIn,
    session: Session = Depends(current_session),
    store: Store = Depends(get_store),
    today: date = Depends(get_today),
) -> dict:
    return public_explained(engine.check_impulse(store.load(session.user_id), body.amount, today))
