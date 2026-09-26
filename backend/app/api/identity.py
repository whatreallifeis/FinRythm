"""Вход через Telegram Mini App: проверка подписи initData ключом бота."""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class TelegramAuthError(Exception):
    def __init__(self, message: str, *, not_configured: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.not_configured = not_configured


def user_id_for_telegram(telegram_id: int, salt: str) -> str:
    """Один и тот же Telegram-пользователь всегда получает один и тот же user_id."""
    digest = hashlib.sha256(f"{salt}:{telegram_id}".encode()).hexdigest()[:16]
    return f"tg:{digest}"


def sign_init_data(fields: dict[str, str], bot_token: str) -> str:
    """Хеш initData так, как его считает Telegram. Нужен проверке и тестам."""
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()


def verify_init_data(
    init_data: str, bot_token: str, *, max_age_seconds: int = 86_400, now: float | None = None
) -> dict:
    """Возвращает {"id": telegram_id, "displayName": имя}. Любая проблема — TelegramAuthError."""
    if not bot_token:
        raise TelegramAuthError("Вход через Telegram не настроен: не задан токен бота.", not_configured=True)
    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    received = fields.pop("hash", None)
    if not received:
        raise TelegramAuthError("Telegram не прислал подпись. Откройте приложение из чата с ботом.")
    if not hmac.compare_digest(sign_init_data(fields, bot_token), received):
        raise TelegramAuthError("Telegram не подтвердил вход.")
    try:
        auth_date = int(fields.get("auth_date", "0"))
    except ValueError as error:
        raise TelegramAuthError("Telegram прислал некорректную дату входа.") from error
    if (now if now is not None else time.time()) - auth_date > max_age_seconds:
        raise TelegramAuthError("Сессия Telegram устарела. Закройте приложение и откройте снова.")
    try:
        user = json.loads(fields.get("user", ""))
        telegram_id = int(user["id"])
    except (TypeError, ValueError, KeyError) as error:
        raise TelegramAuthError("Telegram не передал профиль пользователя.") from error
    name = " ".join(part for part in (user.get("first_name"), user.get("last_name")) if part).strip()
    return {"id": telegram_id, "displayName": name or "Пользователь"}
