"""Наполнение данными: демо-набор и импорт операций (CSV разбирает фронтенд, присылает строки)."""

from datetime import date

from fastapi import APIRouter, Depends, Response

from app.api import engine
from app.api.deps import current_session, get_store, get_today
from app.api.schemas import ImportIn
from app.api.serialize import to_json
from app.storage import Session, Store

router = APIRouter()


@router.post("/demo/seed", status_code=204)
def seed_demo(session: Session = Depends(current_session), store: Store = Depends(get_store)) -> Response:
    history = store.load(session.user_id).history
    state = engine.load_demo_state()
    state.history = history  # сохранённые диалоги не теряем
    store.save(session.user_id, state)
    return Response(status_code=204)


@router.post("/transactions/import")
def import_transactions(
    body: ImportIn,
    session: Session = Depends(current_session),
    store: Store = Depends(get_store),
    today: date = Depends(get_today),
) -> dict:
    state, result = engine.apply_import(store.load(session.user_id), body.rows, today)
    store.save(session.user_id, state)
    return to_json(result)
