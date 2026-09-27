"""Эндпоинты в форме, которую ждёт фронтенд (ветка front, frontend/src/shared/api/client.ts)."""

from fastapi import APIRouter

from app.api.routes import analysis, assistant, calendar, data, goals, profile, session

router = APIRouter(prefix="/api")
for module in (session, profile, data, analysis, goals, assistant, calendar):
    router.include_router(module.router)

__all__ = ["router"]
