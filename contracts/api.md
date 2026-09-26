# Контракт HTTP API «ФинРитм»

Владелец: **Вероника**. Реализация: `backend/app/api/`. Живая документация: `http://localhost:8000/docs`.

API сделан под фронтенд ruina696 (ветка `front`): формы ответов — `frontend/src/shared/api/types.ts`,
вызовы — `frontend/src/shared/api/client.ts`. **Указания ruina696 по бэкенду в приоритете**: если этот файл
с ними расходится, прав фронтенд, а этот файл надо поправить (issue `to:veronika`).

## Общие правила

- Базовый путь `/api`, JSON, UTF-8. Поля в JSON — **camelCase**.
- Деньги в JSON — **числа** в рублях с копейками (`18430.5`): так ждёт фронтенд. Внутри бэкенда — только `Decimal`;
  в число сумма превращается один раз, в `app.api.serialize`.
- Даты — `ГГГГ-ММ-ДД`. Дата расчёта — переменная `APP_TODAY` (для демо `2026-09-26`), иначе сегодня.
- Ошибки — один формат, сообщения по-русски:
  ```json
  {"error": {"code": "validation_error", "message": "Дата в формате ГГГГ-ММ-ДД", "field": "rows.0.date"}}
  ```
  Коды: `validation_error` 422, `unauthorized` 401, `not_found` 404, `rate_limited` 429, `llm_unavailable` 503, `internal` 500.
- Нехватка данных — **не ошибка**: 200 и `dataQuality.sufficient = false` со списком `missing`.

## Вход

| Клиент | Как |
|---|---|
| Сайт | `POST /api/auth/demo` → `Session` |
| Telegram Mini App | `POST /api/auth/telegram` `{initData}` → `Session`. Подпись initData проверяется ключом бота; один Telegram-пользователь — всегда один `userId` |

`Session = {token, userId, displayName, mode: "demo" | "telegram"}`.
Дальше каждый запрос — с заголовком `Authorization: Bearer <token>`, иначе 401.

## Обёртка объяснимости `Explained<T>`

Все аналитические ответы и ответ помощника:
```json
{
  "result": { ... },
  "assumptions": ["Период: 2026-09-01 — 2026-09-26."],
  "calculation": [{"label": "Можно тратить в день", "formula": "7 800 ₽ / 12 дн.", "value": 650}],
  "sources": [{"title": "Банк России", "url": "https://..."}],
  "limitations": ["Это не финансовая рекомендация."],
  "dataQuality": {"sufficient": true, "missing": [], "coverageDays": 61}
}
```

## Эндпоинты

| Метод и путь | Тело | Ответ | Кто считает |
|---|---|---|---|
| `GET /api/health` | — | `{status, llm_provider, version}` | — |
| `POST /api/auth/demo` | — | `Session` | — |
| `POST /api/auth/telegram` | `{initData}` | `Session` (401 — подпись неверна, 503 — бот не настроен) | — |
| `GET /api/profile` | — | `Profile = {balance, incomes[{id,title,amount,dayOfMonth}], goals[Goal]}` | — |
| `PUT /api/profile` | `{balance, incomes[{id?,title,amount,dayOfMonth}]}` | `Profile` | — |
| `POST /api/demo/seed` | — | 204. Демо-набор студента (история диалогов сохраняется) | `core.load_demo_state` |
| `DELETE /api/dataset` | — | 204. Очистить все данные | — |
| `GET /api/transactions` | — | `Transaction[] = {id,date,amount,category,merchant,isRecurring}`, новые сверху | — |
| `POST /api/transactions/import` | `{rows: [{date, amount, category, merchant}]}` (≤ 5 000; CSV разбирает фронтенд) | `ImportResult = {imported, rejected[{row,message}], warnings[]}` | `ingest.apply_import` |
| `GET /api/analysis/overview` | — | `Explained<Overview>` | `core.build_overview` |
| `GET /api/analysis/forecast` | — | `Explained<Forecast>` | `core.build_forecast` |
| `GET /api/analysis/runway` | — | `Explained<Runway>` | `core.build_runway` |
| `POST /api/analysis/impulse` | `{amount}` (> 0) | `Explained<ImpulseCheck>` | `core.check_impulse` |
| `POST /api/goals` | `GoalDraft = {title, targetAmount, savedAmount, deadline \| null}` | 201, `Goal` | — |
| `PATCH /api/goals/{id}` | `GoalDraft` | `Goal` (404 — «Цель не найдена.») | — |
| `DELETE /api/goals/{id}` | — | 204 (404) | — |
| `GET /api/goals/{id}/plan` | — | `Explained<GoalPlan>` (404) | `core.build_goal_plan` |
| `POST /api/ask` | `{question (1–1000), scenarioId}` | `Explained<{text}>`; 429 — больше 20 вопросов в минуту; 503 — LLM недоступен | `ai.ask` |
| `GET /api/history` | — | `HistoryEntry[]`, новые сверху | — |
| `PUT /api/history/{id}` | `HistoryEntry = {id, scenarioId, title, createdAt, messages[]}` | `HistoryEntry` (сервер хранит как прислали) | — |
| `DELETE /api/history` | — | 204 | — |

`scenarioId`: `expenses` | `budget` | `glossary` | `impulse` | `free` (промпты — `docs/ai-scenarios.md` в ветке `front`).
`category`: `food` | `transport` | `subscriptions` | `entertainment` | `health` | `education` | `rent` | `other`.
Поля `Overview`, `Forecast`, `Runway`, `ImpulseCheck`, `GoalPlan` — ровно как в `types.ts`.

## Как API вызывает core, ingest и ai

`app/api/engine.py` вызывает функции ниже напрямую, без заглушек. Сигнатуры (модели — раздел «Модели фронтенда» в `backend/app/models.py`):

```python
# app.core (Саша)
build_overview(state: UserState, as_of: date) -> Explained
build_forecast(state: UserState, as_of: date) -> Explained
build_runway(state: UserState, as_of: date) -> Explained
check_impulse(state: UserState, amount: Decimal, as_of: date) -> Explained
build_goal_plan(state: UserState, goal_id: str, as_of: date) -> Explained | None   # None → 404
load_demo_state() -> UserState
# app.ingest (Саша)
apply_import(state: UserState, rows: list[ImportRow], as_of: date) -> tuple[UserState, ImportResult]
# app.ai (Соня)
async ask(question: str, scenario_id: ScenarioId, state: UserState, as_of: date, *, llm, kb) -> Explained
load_kb(path: str) -> KnowledgeBase          # нет файла — пустая база
class LLMUnavailable(Exception)              # API превращает в 503
```

В `Explained.result` ключи — camelCase как в `types.ts`, деньги — `Decimal`, даты — `date`: переводит API.

## Статика

Если есть `frontend/dist`, сервер отдаёт его по `/`. Иначе `/` → редирект на `/docs`.
