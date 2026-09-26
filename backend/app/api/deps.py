"""Зависимости FastAPI: настройки, хранилище, текущая сессия, дата расчёта."""

from collections.abc import Iterator
from datetime import date

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

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


# В Swagger (/docs) появляется кнопка Authorize: токен из POST /api/auth/demo вставляется один раз.
bearer = HTTPBearer(auto_error=False, description="Токен из POST /api/auth/demo")


def current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer), store: Store = Depends(get_store)
) -> Session:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Нужно войти, чтобы видеть свои данные.")
    session = store.session(credentials.credentials.strip())
    if session is None:
        raise HTTPException(status_code=401, detail="Сессия недействительна. Войдите снова.")
    return session
