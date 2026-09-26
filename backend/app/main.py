"""
ФинРитм API.

Слои:
  routes  — HTTP в форме, которую уже ждёт фронтенд
  core    — суммы, доли, календарь до поступления, план цели (только Decimal)
  ai      — текст вокруг уже посчитанных чисел, справочник с источниками, отказ на рискованные вопросы
  storage — профиль пользователя в SQLite

Модель не считает деньги. Если данных не хватает, ответ честно говорит, чего не хватает.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routes import get_store, router
from app.storage import Store, connect


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title="ФинРитм", version="0.1.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def store_dependency():
        path = Path(settings.database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = connect(str(path))
        try:
            yield Store(connection)
        finally:
            connection.close()

    application.dependency_overrides[get_store] = store_dependency
    application.include_router(router)

    @application.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        message = "Проверьте введённые данные."
        errors = exc.errors()
        if errors:
            detail = errors[0].get("msg", "")
            if isinstance(detail, str) and detail:
                message = detail.removeprefix("Value error, ")
        return JSONResponse(
            status_code=422, content={"error": {"code": "validation_error", "message": message}}
        )

    return application


app = create_app()
