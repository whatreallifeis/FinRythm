"""Подпись Telegram initData проверяется только здесь, ключом бота."""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class TelegramAuthError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def user_id_for_telegram(telegram_id: int, salt: str) -> str:
    digest = hashlib.sha256(f"{salt}:{telegram_id}".encode()).hexdigest()[:16]
    return f"tg:{digest}"


def verify_init_data(init_data: str, bot_token: str, *, max_age_seconds: int = 86_400) -> dict:
    if not bot_token:
        raise TelegramAuthError("Вход через Telegram не настроен: не задан токен бота.")
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received = parsed.pop("hash", None)
    if not received:
        raise TelegramAuthError("Telegram не прислал подпись. Откройте приложение из чата с ботом.")
    check = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, received):
        raise TelegramAuthError("Telegram не подтвердил вход.")
    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except ValueError as error:
        raise TelegramAuthError("Telegram прислал некорректную дату входа.") from error
    if time.time() - auth_date > max_age_seconds:
        raise TelegramAuthError("Сессия Telegram устарела. Закройте приложение и откройте снова.")
    try:
        user = json.loads(parsed.get("user", ""))
        telegram_id = int(user["id"])
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise TelegramAuthError("Telegram не передал профиль пользователя.") from error
    name = " ".join(part for part in (user.get("first_name"), user.get("last_name")) if part).strip()
    return {"id": telegram_id, "displayName": name or "Пользователь"}
