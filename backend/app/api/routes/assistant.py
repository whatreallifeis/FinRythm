"""Помощник (POST /api/ask) и история диалогов.

Промпт по scenarioId подставляет ai (Соня). Числа в ответе посчитаны core, а не моделью.
Текст вопросов в логи не пишем.
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api import engine
from app.api.deps import current_session, get_store, get_today
from app.api.schemas import AskIn, HistoryEntryIn
from app.api.serialize import public_explained
from app.storage import Session, Store

log = logging.getLogger("finritm")
router = APIRouter()

LLM_DOWN = "Помощник временно недоступен. Расчёты на экранах «Обзор» и «Цели» работают."


@router.post("/ask")
async def ask(
    body: AskIn,
    request: Request,
    session: Session = Depends(current_session),
    store: Store = Depends(get_store),
    today: date = Depends(get_today),
) -> dict:
    if not request.app.state.ask_limiter.allow(session.user_id):
        raise HTTPException(status_code=429, detail="Слишком много вопросов подряд. Подождите минуту.")
    llm = request.app.state.llm
    if llm is None:
        raise HTTPException(status_code=503, detail=LLM_DOWN)
    state = store.load(session.user_id)
    try:
        answer = await engine.ask(
            body.question.strip(), body.scenario_id, state, today, llm=llm, kb=request.app.state.kb
        )
    except engine.llm_errors() as error:
        log.warning("llm unavailable: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail=LLM_DOWN) from error
    return public_explained(answer)


@router.get("/history")
def read_history(
    session: Session = Depends(current_session), store: Store = Depends(get_store)
) -> list[dict]:
    history = store.load(session.user_id).history
    return sorted(history, key=lambda entry: str(entry.get("createdAt", "")), reverse=True)


@router.put("/history/{entry_id}")
def save_history(
    entry_id: str,
    body: HistoryEntryIn,
    session: Session = Depends(current_session),
    store: Store = Depends(get_store),
) -> dict:
    if body.id != entry_id:
        raise HTTPException(status_code=422, detail="Идентификатор в адресе и в теле не совпадает.")
    entry = body.model_dump(by_alias=True)
    state = store.load(session.user_id)
    state.history = [item for item in state.history if item.get("id") != entry_id] + [entry]
    store.save(session.user_id, state)
    return entry


@router.delete("/history", status_code=204)
def clear_history(session: Session = Depends(current_session), store: Store = Depends(get_store)) -> Response:
    state = store.load(session.user_id)
    state.history = []
    store.save(session.user_id, state)
    return Response(status_code=204)
