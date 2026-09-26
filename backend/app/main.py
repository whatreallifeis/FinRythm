"""
ФинРитм API.

Слои:
  api     — HTTP в форме, которую ждёт фронтенд (camelCase, деньги числами)
  core    — все расчёты денег (Decimal), ingest — импорт операций
  ai      — текст вокруг уже посчитанных чисел
  storage — сессии и данные пользователя в SQLite

Запуск: uvicorn app.main:app --reload --app-dir backend
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import errors
from app.api.routes import router
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    app = FastAPI(title="ФинРитм API", version=settings.git_sha)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    errors.install(app)
    app.include_router(router)
    return app


app = create_app()
