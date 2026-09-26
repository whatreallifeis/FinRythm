# Статус: sasha

Обновляется в конце каждой задачи. Последнее обновление: 27.09.2026, S13 (прод)

## Сделано
- **S1. Заглушки core в main, можно подключать.** Все функции из `docs/tasks/sasha.md` экспортируются из `app.core` и `app.ingest`, возвращают валидные модели. `calculate_runway` пока всегда отдаёт числа P1 из `expected_results.json`.

- **S2. Дневной лимит и «что если».** `calculate_runway` и `simulate` считают по §6.1; все 9 эталонов `expected_results.json` совпадают до копейки (`backend/tests/core/test_expected_results.py`). Полный `RunwayResult`: `mandatory_items`, `next_income_title`, `assumptions`, `missing`, `formula_text`. В `core/money.py`: `to_money`, `floor_rub`, `ceil_rub`, `fmt_num`, `fmt_rub`, `days_word`.

- **S3. План цели.** `plan_goal`, `plan_all_goals` по §6.2; эталон `goal_plan.p1_laptop` совпадает (323 ₽, 18 600 ₽, 2028-05-18).

- **SF1. Эталон ветки front.** Её API прогнан на демо-данных 26.09.2026. Сценарий `handoff.md` сходится: лимит 475 ₽ в день до стипендии 5 октября; покупка 14 900 ₽ → `shortfall`, ждать «Подработку» 10 октября; 3 000 ₽ → `wait` (до стипендии); 500 ₽ → `ok` (лимит 420 ₽). Пять ошибок в расчётах описаны в #12 (@ruina696), в core они исправляются.

- **SF2. Демо-данные.** `data/demo/student.json` (формат `UserState`): баланс 18 430 ₽, стипендия 8 000 ₽ 5-го, подработка 25 000 ₽ 10-го, цели «Ноутбук для учёбы» (срок 01.02.2027) и «Финансовая подушка» (без срока), 25 операций за август–сентябрь. `from app.core import load_demo_state, DEMO_AS_OF` → `load_demo_state() -> UserState` (каждый раз новая копия), `DEMO_AS_OF = 2026-09-26`.

- **SF3. Расчёты нового API.** В `app.core` — чистые функции на `UserState`, каждая возвращает `Explained` (`result` с ключами как в `types.ts`, деньги `Decimal`, даты — строки ISO):
  `build_runway(state, as_of)`, `check_impulse(state, amount, as_of)`, `build_forecast(state, as_of)`, `build_overview(state, as_of)`, `build_goal_plan(state, goal_id, as_of)` (`None` — цели нет → 404), `coverage_days(transactions, as_of) -> int`, `mark_recurring(transactions) -> list[Operation]`.
  Лимит на день и проверка покупки считаются одним календарём (`core/runway_calendar.py`). Числа эталона SF1 совпадают до копейки, кроме исправлений из #12.

- **SF4. Импорт строк от фронтенда.** `from app.ingest import apply_import` → `apply_import(state, rows: list[ImportRow], as_of) -> tuple[UserState, ImportResult]`. Исходный `state` не меняется. Отказ строки (номер с 1): нулевая сумма, сумма ≥ 10 млрд, дата в будущем, пустое описание, описание длиннее 200 символов, номер карты (13+ цифр подряд, можно через пробел или дефис, в любом месте описания — в ветке front «Перевод 4276 … от 12.09» проходил, #12). Неизвестная категория → `other` с предупреждением; дубликат (дата + сумма + магазин без учёта регистра) → пропуск с предупреждением; ничего нового → «Новых операций нет.». `id` новой операции — `imp-` + sha1(дата|сумма|магазин)[:12], одинаковый для одинаковой строки. В конце — `mark_recurring` по всем операциям.

- **S12. Сквозные тесты нового API** (`tests/e2e/`, только HTTP, без кода бэкенда). Сценарий фронтенда: `auth/demo` → `demo/seed` → профиль и операции → все `/api/analysis/*` → покупка 14 900 / 3 000 / 500 ₽ → цели (план, создание, правка, удаление, 404) → `/api/ask` по каждому `scenarioId`. Плюс правила: 401 без сессии, данные пользователей не смешиваются, нехватка данных — 200 и `sufficient=false`, 422 с русским текстом (сумма ≤ 0, отрицательный баланс, накоплено больше цели, неизвестный сценарий, дата не ГГГГ-ММ-ДД), импорт (номер карты, ноль, будущее, неизвестная категория, дубликат), история, очистка.
  Запуск: `API_BASE_URL=http://localhost:8000 pytest -m e2e`. Точные числа демо проверяются, только если сервер считает на 26.09.2026 (`APP_TODAY=2026-09-26`), иначе эти 8 тестов пропускаются.
  Прогон на VF2 (#17), локально влитом с `main`: 40 из 41 зелёные. Падает `test_demo_overview_numbers` — API округляет `share` до сотых (0.3945 → 0.39), issue #24 для Вероники. На сервере без `APP_TODAY`: 33 зелёных, 8 пропущено.

## В работе
- **S13. QA на проде** — стенд https://134-0-113-6.sslip.io, версия `ea8fc14`, `APP_TODAY=2026-09-26`, модель qwen2.5:3b на CPU.
  - **e2e без помощника: 32 из 33.** Числа демо сходятся (475 ₽, стипендия 5 октября, 14 900 ₽ → «Подработка» 10 октября). Падает только `share` 0.3945 → 0.39 (#24).
  - **e2e помощника (`E2E_TIMEOUT=150`): 7 из 8.** `impulse` 28 с, `budget` 27 с, `glossary` 39 с (с источником), `expenses` — 503 через 45 с. Повторный запрос висел больше 150 с. Детали в #39 (Соня).
  - **10 рискованных вопросов** — все правильно, 0,1 с, модель не вызывается. «Реши за меня»: вариант «не покупать» есть, но модель убирает «решать вам» (#39).
  - **Образцы CSV из ветки front:** 17 из 17; «плохой» — отказ по будущей дате с номером строки из списка, а не из файла (#36).
  - **Не проверено:** экраны фронтенда в браузере (сайт закрыт паролем, пароля у меня нет) — п.1–3, 7, 9 чек-листа `docs/03_deploy.md` надо пройти руками.
  - Запуск против прода: `API_BASE_URL=https://134-0-113-6.sslip.io E2E_TIMEOUT=150 pytest -m e2e`.
  - Изменение в tests/e2e: таймаут HTTP-клиента задаётся через `E2E_TIMEOUT` (по умолчанию 30 с).

## Заблокировано / жду от других
- #24 (`share`), #36 (номера строк импорта) — Вероника; #39 (скорость и таймауты модели) — Соня.

## Что важно знать остальным
- **Новый API (SF3):** `from app.core import build_runway, check_impulse, build_forecast, build_overview, build_goal_plan, coverage_days, mark_recurring, load_demo_state, DEMO_AS_OF`. При нехватке данных `data_quality.sufficient=False`, `missing` по-русски («текущий баланс», «хотя бы одно регулярное поступление с днём месяца», «операции хотя бы за один месяц», «операции за текущий месяц», «срок, к которому нужна сумма»), `result` — пустой ответ той же формы. `check_impulse` с суммой ≤ 0 → `ValueError` (API проверяет раньше, 422).
- **Отличия от ветки front (#12):** прогноз не даёт лимит больше календарного и откладывает деньги на платежи сразу после конца месяца (демо: 475 ₽ и `tight`, а не 4 607 ₽ и `ok`); аренда не «разовая трата»; `deltaPercent` — к тем же дням прошлого месяца; накопленная цель не требует срока; `mark_recurring` не делает «Супермаркет» платежом (нужны ≥2 месяца, не чаще раза в месяц, разброс сумм ≤10%).
- В текстах (`hint`, `formula`, допущения) суммы через `fmt_rub`: неразрывный пробел между разрядами («14 900 ₽»).
- Импорт: `from app.core import calculate_runway, simulate, plan_goal, plan_all_goals, build_snapshot, categorize, detect_recurring, spending_breakdown, detect_risks`; `from app.ingest import import_csv`.
- Все функции чистые, дата — `today or profile.as_of or date.today()`.
- Заглушки: `spending_breakdown` — пустой `Breakdown`, `detect_risks` — `RiskReport(risks=[])`, `import_csv` — профиль без изменений и пустой отчёт, `build_snapshot` — dict с ключами `as_of, balance, next_confirmed_income, expected_incomes, payments_next_30_days, goals, missing` (деньги строками).
- `fmt_rub`: неразрывный пробел (U+00A0) между разрядами, минус — U+2212: «9 800 ₽», «785,10 ₽», «−700 ₽». Тот же формат в `formula_text` и текстах допущений — учитывайте при разборе чисел (A5 у Сони).
- `RunwayResult.balance` — баланс из профиля (без вычета покупки); покупка видна в `formula_text` и допущении `purchase`.
- Коды допущений: `horizon_default`, `income_today`, `no_payments`, `expected_income_counted`, `expected_income_ignored`, `goal_paused`, `reserve`, `delay`, `purchase`.
- `plan_goal`: `current_daily` берётся из цели с `goal_id`, иначе 0 (`projected_date=None`). Срок прошёл/сегодня → `required_daily` = вся недостающая сумма, `on_track=False`. Уже накоплено ≥ цели → `required_daily=0`, `on_track=True`, `projected_date=as_of`.
