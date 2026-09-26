"""
ФинРитм API.

Слои:
  api     — HTTP в форме, которую ждёт фронтенд (camelCase, деньги числами)
  core    — все расчёты денег (Decimal), ingest — импорт операций
  ai      — текст вокруг уже посчитанных чисел
  storage — сессии и данные пользователя в SQLite

Запуск: uvicorn app.main:app --reload --app-dir backend
"""

import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.ai import get_llm
from app.api import engine, errors
from app.api.limits import RateLimiter
from app.api.routes import router
from app.config import Settings, get_settings

log = logging.getLogger("finritm")
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _startup(app: FastAPI, settings: Settings) -> None:
    if settings.openai_project_id and not os.environ.get("OPENAI_PROJECT_ID"):
        # uvicorn читает .env только в Settings, а клиент openai (Алиса AI) — из окружения.
        os.environ["OPENAI_PROJECT_ID"] = settings.openai_project_id
    try:
        app.state.llm = get_llm(settings)
    except ValueError as error:  # неизвестный LLM_PROVIDER: API работает, помощник отвечает 503
        log.error("LLM не настроен: %s", error)
        app.state.llm = None
    try:
        app.state.kb = engine.load_kb(settings.kb_path)
    except (OSError, ValueError) as error:
        log.error("База знаний не загружена: %s", error)
        app.state.kb = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _startup(app, settings)
        yield

    app = FastAPI(title="ФинРитм API", version=settings.git_sha, lifespan=lifespan)
    app.state.settings = settings
    app.state.llm = None
    app.state.kb = None
    app.state.ask_limiter = RateLimiter(settings.ask_limit_per_minute)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            # Только путь, статус и время: ни тела запроса, ни токена в логах.
            line = {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": round((time.perf_counter() - started) * 1000),
            }
            log.info(json.dumps(line, ensure_ascii=False))
        return response

    errors.install(app)
    app.include_router(router)

    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    else:

        @app.get("/", include_in_schema=False)
        def root() -> RedirectResponse:
            return RedirectResponse("/docs")

    return app


app = create_app()
