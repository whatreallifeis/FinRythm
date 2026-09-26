# Контракт HTTP API «ФинРитм»

Владелец: **Вероника**. Реализация: `backend/app/api/`. Модели запросов и ответов — `backend/app/models.py`.
Живая документация после запуска: `http://localhost:8000/docs` (Swagger) и `/openapi.json`.
Этот API используют Telegram-бот (Кирилл), e2e-тесты (Кирилл), а позже — фронтенд (сайт и Mini App).

## Общие правила

- Базовый путь: `/api`. Формат: JSON, UTF-8. Деньги в JSON — **строки** (`"9800.00"`), чтобы не терять точность.
- Все ошибки возвращаются в одном формате `ErrorResponse`:
  ```json
  {"error": {"code": "validation_error", "message": "Сумма должна быть больше нуля", "field": "payments[0].amount", "row": null}}
  ```
  Коды: `validation_error` (422), `not_found` (404), `unauthorized` (401), `insufficient_data` (200 со статусом в теле, не ошибка), `llm_unavailable` (503), `internal` (500).
- Сообщения об ошибках — **по-русски**, понятные пользователю.
- CORS: разрешены origin из переменной `CORS_ORIGINS` (для будущего фронтенда).

## Идентификация пользователя

Данные синтетические, поэтому авторизация упрощённая. Один из трёх способов:

| Клиент | Как | Что делает сервер |
|---|---|---|
| Сайт | `POST /api/session` → получить `user_id`, дальше заголовок `X-User-Id: <user_id>` | Создаёт анонимный профиль (`web:<uuid4>`) |
| Telegram-бот | Заголовки `X-Bot-Secret: <BOT_API_SECRET>` и `X-Telegram-User-Id: <id>` | Проверяет секрет, `user_id = tg:<sha256(TG_ID_SALT + id)[:16]>` |
| Telegram Mini App | `POST /api/auth/telegram` с `init_data` → получить `user_id`, дальше `X-User-Id` | Проверяет подпись initData (HMAC-SHA256, ключ = HMAC("WebAppData", BOT_TOKEN)), `user_id` вычисляется **так же, как для бота** |

Благодаря одинаковой функции `user_id` у пользователя **один профиль** в боте и в Mini App. Функция живёт в `backend/app/api/identity.py`.

## Эндпоинты

| Метод и путь | Тело запроса | Ответ | Назначение |
|---|---|---|---|
| `GET /api/health` | — | `{"status":"ok","llm_provider":"fake","version":"..."}` | Проверка живости |
| `POST /api/session` | — | `SessionResponse` | Анонимная сессия для сайта |
| `POST /api/auth/telegram` | `TelegramAuthRequest` | `SessionResponse` | Вход из Mini App |
| `GET /api/profile` | — | `Profile` | Текущие данные (пустой профиль, если нет) |
| `PUT /api/profile` | `Profile` | `Profile` | Полная замена данных (ручной ввод). `origin.kind = "manual"` ставит сервер |
| `DELETE /api/profile` | — | `204` | Очистить данные |
| `POST /api/profile/demo/{name}` | — | `Profile` | Загрузить демо-профиль: `p1`, `p2`, `p3` (из `data/demo/`) |
| `POST /api/transactions/import?mode=append\|replace` | `multipart/form-data`, поле `file` (CSV, ≤ 1 МБ) | `ImportReport` | Импорт CSV |
| `GET /api/summary` | — | `SummaryResponse` | Всё для дашборда: лимит, структура, риски, цели, происхождение данных |
| `POST /api/simulate` | `SimulateRequest` | `SimulationResult` | «Что если» |
| `POST /api/goal/plan` | `GoalPlanRequest` | `GoalPlan` | План накопления |
| `POST /api/chat` | `ChatRequest` | `ChatResponse` | Вопрос AI-ассистенту |
| `GET /api/chat/stream?message=...` | — | SSE: события `step` (вызов инструмента), `answer` (финальный `ChatResponse`) | Опционально (приоритет S) |

## Поведение при неполных данных

- `balance == null` → `GET /api/summary` возвращает `runway.status = "insufficient_data"` и список `runway.missing`. Это **не HTTP-ошибка**.
- Нет обязательных платежей → расчёт выполняется, в `assumptions` добавляется `no_payments`.
- Нет подтверждённого поступления → горизонт 30 дней, `horizon_is_assumed = true`, допущение `horizon_default`.
- Нет транзакций → `breakdown = null`, риск `no_data` с текстом «Загрузите операции, чтобы увидеть структуру расходов».

## Статика

Если существует папка `frontend/dist`, сервер отдаёт её по `/` (для будущего фронтенда). Иначе `/` делает редирект на `/docs`.
