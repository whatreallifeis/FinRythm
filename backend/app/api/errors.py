"""Единый формат ошибок: {"error": {"code", "message", "field"}}. Сообщения — по-русски."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("finritm")

STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "too_large",
    422: "validation_error",
    429: "rate_limited",
    503: "llm_unavailable",
}


def _validation_message(error: dict) -> str:
    kind = error.get("type", "")
    ctx = error.get("ctx") or {}
    match kind:
        case "missing":
            return "Обязательное поле"
        case "greater_than":
            return f"Значение должно быть больше {ctx.get('gt')}"
        case "greater_than_equal":
            return f"Значение должно быть не меньше {ctx.get('ge')}"
        case "less_than_equal":
            return f"Значение должно быть не больше {ctx.get('le')}"
        case "decimal_parsing" | "decimal_type" | "float_parsing" | "float_type" | "int_parsing" | "int_type":
            return "Нужно число"
        case "decimal_max_digits":
            return "Слишком большое число"
        case "decimal_max_places":
            return "Не больше двух знаков после запятой"
        case "date_parsing" | "date_from_datetime_parsing" | "date_type" | "date_from_datetime_inexact":
            return "Дата в формате ГГГГ-ММ-ДД"
        case "extra_forbidden":
            return "Неизвестное поле"
        case "literal_error" | "enum":
            return "Недопустимое значение"
        case "string_too_short":
            return "Поле не может быть пустым"
        case "string_too_long":
            return f"Слишком длинное значение: не больше {ctx.get('max_length')} символов"
        case "too_long":
            return f"Слишком много элементов: не больше {ctx.get('max_length')}"
        case "json_invalid":
            return "Некорректный JSON"
        case "string_type":
            return "Нужен текст"
        case "bool_type" | "bool_parsing":
            return "Нужно да или нет"
        case "list_type":
            return "Нужен список"
        case "dict_type" | "model_type" | "model_attributes_type":
            return "Нужен объект"
        case "value_error":
            message = str(error.get("msg", ""))
            return message.removeprefix("Value error, ") or "Проверьте введённые данные"
    return "Проверьте введённые данные"


def _field(error: dict) -> str | None:
    if error.get("type") == "json_invalid":
        return None  # в loc — позиция символа в теле, а не поле
    parts = [str(part) for part in error.get("loc", ()) if part not in ("body", "query", "path")]
    return ".".join(parts) or None


def error_body(code: str, message: str, field: str | None = None) -> dict:
    return {"error": {"code": code, "message": message, "field": field}}


def install(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        return JSONResponse(
            status_code=422,
            content=error_body("validation_error", _validation_message(first), _field(first)),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = STATUS_CODES.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "Ошибка запроса"
        if exc.status_code == 404 and message == "Not Found":
            message = "Такой страницы нет"
        if exc.status_code == 405:
            message = "Этот метод здесь не поддерживается"
        return JSONResponse(
            status_code=exc.status_code, content=error_body(code, message), headers=exc.headers
        )

    @app.exception_handler(Exception)
    async def _internal(request: Request, exc: Exception) -> JSONResponse:
        log.exception("internal error on %s", request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=error_body("internal", "Что-то пошло не так на сервере. Попробуйте ещё раз."),
        )
