# ТЗ: Вероника — владелец репозитория, API и инфраструктура

**Роль:** владелец репозитория и интегратор. Ты собираешь части в работающий сервис, отвечаешь за API, хранилище, Docker, CI, деплой и мерж PR.
**Зона:** `backend/app/api/`, `backend/app/storage/`, `backend/app/main.py`, `backend/app/config.py`, `backend/app/models.py` (контракт), `backend/tests/api/`, `Dockerfile`, `docker-compose.yml`, `.github/`, `requirements*.txt`, `pyproject.toml`, `.env.example`, `CLAUDE.md`, `docs/status/veronika.md`.
**Ревьюер твоих PR:** Кирилл. **Ты ревьюишь:** PR Кирилла и все PR с меткой `contract`. **Ты мержишь** одобренные PR (Squash and merge).
**Ты используешь:** core и ingest Саши, `answer()` Сони, демо-данные Кирилла.
**Тобой пользуются:** бот и e2e Кирилла (по HTTP), позже фронтенд.

## Стартовый промпт для Claude Code

```
Я Вероника, владелец репозитория. Ты работаешь на меня в проекте ФинРитм.
Прочитай CLAUDE.md, docs/01_project_spec.md, docs/02_workflow.md, docs/tasks/veronika.md,
contracts/api.md, backend/app/models.py.
Проверь входящие issues: gh issue list --label to:veronika --state open.
Задачу V0 я делаю руками по docs/00_connect.md. Начни с V1.
После каждой задачи: тесты, ruff, обновить docs/status/veronika.md, PR на ревью Кириллу.
Меняй только файлы моей зоны.
```

---

## V0. Репозиторий и доступы · Ч0–0:45 (руками, по `docs/00_connect.md`)

1. Создать **публичный** репозиторий `finritm` (жюри проверяет репозиторий; на публичном бесплатно работает защита веток).
2. Залить стартовый набор (этот архив) первым коммитом.
3. Пригласить Сашу, Соню, Кирилла с ролью **Write**.
4. `scripts/setup_github.sh` — метки `to:*`, `contract`, `blocked`, `bug`.
5. Защита `main`: только через PR, 1 одобрение, обязательный CI.
6. Включить **Squash merging** и **Automatically delete head branches** (Settings → General).
7. Добавить секреты для деплоя (Settings → Secrets and variables → Actions), когда будут ключи.

## V1. Каркас API на заглушках · Ч0:45–2 · СРОЧНО, НУЖНО КИРИЛЛУ

- `config.py`: `Settings` на `pydantic-settings`, все переменные из `.env.example`.
- `main.py`: `FastAPI(title="ФинРитм API")`, CORS, роутеры, обработчики ошибок, `lifespan` (создание БД, `app.state.llm = get_llm(...)`, `app.state.kb = load_kb(...)` — пока Соня не влила, оберни в try/except с заглушкой).
- `api/errors.py`: единый `ErrorResponse`. Для `RequestValidationError` — русские сообщения по типу ошибки pydantic: `missing` → «Обязательное поле», `greater_than` → «Значение должно быть больше {gt}», `decimal_parsing`/`float_parsing` → «Нужно число», `date_from_datetime_parsing`/`date_parsing` → «Дата в формате ГГГГ-ММ-ДД», `extra_forbidden` → «Неизвестное поле»; `field` = путь поля через точку.
- `api/routes/*.py`: **все** эндпоинты из `contracts/api.md`. Пока core не готов — используй заглушки Саши (S1 выходит к Ч1:15); если их ещё нет — верни валидный объект модели с данными P1.
- Тест `tests/api/test_smoke.py`: каждый эндпоинт отвечает нужной моделью.
- Сообщи Кириллу (issue `to:kirill`): «API на заглушках в main, запуск: `uvicorn app.main:app --app-dir backend`».

## V2. Хранилище, идентификация, профиль · Ч2–3

- `storage/db.py`: SQLite, таблица `profiles(user_id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL)`, WAL, соединение на запрос.
- `storage/repo.py`: `ProfileRepo.get(user_id) -> Profile | None`, `save(user_id, profile)`, `delete(user_id)`.
- `api/identity.py` (FastAPI-зависимость `get_user_id`):
  - `X-User-Id` — только формат `web:<uuid4>` или `tg:<16 hex>`, иначе 401;
  - `X-Bot-Secret` + `X-Telegram-User-Id` → проверка секрета (`hmac.compare_digest`), `tg_user_id(id) = "tg:" + sha256(TG_ID_SALT + str(id)).hexdigest()[:16]`;
  - `validate_init_data(init_data, bot_token)`: разобрать query-string, `data_check_string` = отсортированные `key=value` без `hash` через `\n`, `secret = HMAC_SHA256(key="WebAppData", msg=bot_token)`, сравнить `HMAC_SHA256(secret, data_check_string).hex()` с `hash`; `auth_date` не старше 24 ч; `user.id` → `tg_user_id`.
- `POST /api/session`, `POST /api/auth/telegram`, `GET/PUT/DELETE /api/profile`, `POST /api/profile/demo/{name}`: берёт `data/demo/<name>.json`, если есть, иначе `contracts/profiles/<name>.json`; `origin` из файла.
- `PUT /api/profile`: сервер ставит `origin = DataOrigin(kind="manual", label="Данные введены вручную", updated_at=now)`, если не импорт.
- Тесты: идентификация (все три способа + неверный секрет + подделанный initData — сгенерируй валидный initData в тесте с тестовым токеном), CRUD профиля, демо.

## V3. Docker, CI, первый деплой · Ч3–3:45 · КОНТРОЛЬНАЯ ТОЧКА

- `Dockerfile`: `python:3.12-slim`, установка `requirements.txt`, копирование `backend/`, `contracts/`, `data/`, `bot/`; `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend`.
- `docker-compose.yml`: сервис `api` (порт 8000, том `./data-runtime:/app/runtime`, `DATABASE_PATH=/app/runtime/finritm.sqlite3`) и сервис `bot` (тот же образ, `command: python -m bot`, `API_BASE_URL=http://api:8000`, `depends_on: api`). Оба читают `.env`.
- CI уже лежит в `.github/workflows/ci.yml` — проверь, что проходит на твоём первом PR.
- **Деплой** (выбери один вариант и запиши в `docs/status/veronika.md`):
  - VPS (Timeweb Cloud / Selectel / любой): `docker compose up -d` + Caddy для HTTPS на домене или `*.nip.io`/`sslip.io`;
  - Render: Web Service (API) + Background Worker (бот) из Dockerfile;
  - Timeweb Cloud Apps: приложение из Dockerfile (API); бот — вторым приложением.
- Секреты на хостинге — через переменные окружения панели, **не** в репозитории.
- Результат: публичный `https://.../api/health` и `/docs`. Ссылку — в статус и в общий чат.

## V4. Подключение core · Ч3:45–5

- `GET /api/summary`: `calculate_runway`, `spending_breakdown`, `detect_risks`, `plan_all_goals`, `origin` → `SummaryResponse`.
- `POST /api/simulate`, `POST /api/goal/plan`.
- Тесты API на P1–P3: числа совпадают с `contracts/expected_results.json` (через HTTP-ответ).
- **К Ч5 — интеграция 1:** вместе с Кириллом прогнать СЦ-1…СЦ-6 через бота на проде.

## V5. Импорт и чат · Ч5–7

- `POST /api/transactions/import`: `UploadFile`, проверка размера (≤ 1 МБ) и расширения/типа, вызов `import_csv` Саши, `origin = DataOrigin(kind="csv", label=f"Импорт CSV от {дата}, {N} операций", ...)`.
- `POST /api/chat`: загрузить профиль → `await answer(message, profile, llm=app.state.llm, kb=app.state.kb)` → `ChatResponse`. `LLMUnavailable` → 503 `llm_unavailable` «AI временно недоступен. Попробуйте /limit или /spend».
- Ограничение частоты: не больше 20 сообщений в минуту на `user_id` (простой счётчик в памяти).
- Логи (stdout, JSON-строка): `user_hash`, путь, статус, время; для чата — имена инструментов и `number_check_passed`. **Текст сообщений не логировать.**

## V6. Для фронтенда и полировка · Ч7–9

- Примеры (`examples`) в схемах OpenAPI для основных запросов — фронтенд потом сгенерирует типы.
- Раздача `frontend/dist` по `/`, если папка есть; иначе редирект `/` → `/docs`.
- (S) `GET /api/chat/stream` — SSE поверх `answer_stream()` Сони.
- `GET /api/health` возвращает `llm_provider` и версию (git-хеш из переменной `GIT_SHA`).

## V7. Релиз · Ч9–11

- Фриз в Ч9: мержить только исправления.
- Финальный деплой, тег `git tag v1.0 && git push --tags`.
- Проверка секретов: `git log -p | grep -iE "api_key|token|secret" ` — только имена переменных; gitleaks в CI зелёный.
- В Ч11 — прогон демо вместе с Кириллом.

## Мерж и контракты — постоянно
- Ответ на PR — в течение 20 минут. Порядок мержа: сначала заглушки и контракты, потом остальное.
- PR `contract`: проверь, что затронутые владельцы в ревьюерах; после мержа — сообщение в общий чат.
- Запросы на зависимости (`to:veronika`): добавляешь в `requirements.txt` отдельным маленьким PR.

## Критерии приёмки зоны
- [ ] Все эндпоинты `contracts/api.md` работают, формат ошибок единый, сообщения по-русски.
- [ ] Бот и Mini App получают один и тот же профиль для одного Telegram-пользователя.
- [ ] Публичный HTTPS-адрес работает, `docker compose up --build` поднимает всё локально.
- [ ] CI и gitleaks зелёные, `main` защищён, история чистая.
