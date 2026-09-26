"""Эндпоинты в форме, которую ждёт фронтенд (ветка front, frontend/src/shared/api/client.ts)."""

from fastapi import APIRouter

from app.api.routes import profile, session

router = APIRouter(prefix="/api")
router.include_router(session.router)
router.include_router(profile.router)

__all__ = ["router"]
