"""Зависимости FastAPI: настройки, хранилище, текущая сессия, дата расчёта."""

from collections.abc import Iterator
from datetime import date

from fastapi import Depends, HTTPException, Request

from app.config import Settings
from app.storage import Session, Store, connect


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(settings: Settings = Depends(get_settings)) -> Iterator[Store]:
    connection = connect(settings.database_path)
    try:
        yield Store(connection)
    finally:
        connection.close()


def get_today(settings: Settings = Depends(get_settings)) -> date:
    return settings.app_today or date.today()


def current_session(request: Request, store: Store = Depends(get_store)) -> Session:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Нужно войти, чтобы видеть свои данные.")
    session = store.session(token.strip())
    if session is None:
        raise HTTPException(status_code=401, detail="Сессия недействительна. Войдите снова.")
    return session
