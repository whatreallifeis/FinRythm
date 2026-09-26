"""Живость сервера и вход: демо-сессия для сайта и вход из Telegram Mini App."""

import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_settings, get_store
from app.api.identity import TelegramAuthError, user_id_for_telegram, verify_init_data
from app.api.schemas import TelegramIn
from app.config import Settings
from app.storage import Session, Store

router = APIRouter()


def _public_session(session: Session) -> dict:
    return {
        "token": session.token,
        "userId": session.user_id,
        "displayName": session.display_name,
        "mode": session.mode,
    }


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    return {"status": "ok", "llm_provider": settings.llm_provider, "version": settings.git_sha}


@router.post("/auth/demo")
def auth_demo(store: Store = Depends(get_store)) -> dict:
    user_id = f"web:{uuid.uuid4().hex[:16]}"
    return _public_session(store.create_session(user_id, "Демо-режим", "demo"))


@router.post("/auth/telegram")
def auth_telegram(
    body: TelegramIn, settings: Settings = Depends(get_settings), store: Store = Depends(get_store)
) -> dict:
    try:
        user = verify_init_data(body.init_data, settings.telegram_bot_token)
    except TelegramAuthError as error:
        raise HTTPException(status_code=503 if error.not_configured else 401, detail=error.message) from error
    user_id = user_id_for_telegram(user["id"], settings.tg_id_salt)
    return _public_session(store.create_session(user_id, user["displayName"], "telegram"))
