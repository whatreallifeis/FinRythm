# Статус: sasha

Обновляется в конце каждой задачи. Последнее обновление: 27.09.2026, SF2

## Сделано
- **S1. Заглушки core в main, можно подключать.** Все функции из `docs/tasks/sasha.md` экспортируются из `app.core` и `app.ingest`, возвращают валидные модели. `calculate_runway` пока всегда отдаёт числа P1 из `expected_results.json`.

- **S2. Дневной лимит и «что если».** `calculate_runway` и `simulate` считают по §6.1; все 9 эталонов `expected_results.json` совпадают до копейки (`backend/tests/core/test_expected_results.py`). Полный `RunwayResult`: `mandatory_items`, `next_income_title`, `assumptions`, `missing`, `formula_text`. В `core/money.py`: `to_money`, `floor_rub`, `ceil_rub`, `fmt_num`, `fmt_rub`, `days_word`.

- **S3. План цели.** `plan_goal`, `plan_all_goals` по §6.2; эталон `goal_plan.p1_laptop` совпадает (323 ₽, 18 600 ₽, 2028-05-18).

- **SF1. Эталон ветки front.** Её API прогнан на демо-данных 26.09.2026. Сценарий `handoff.md` сходится: лимит 475 ₽ в день до стипендии 5 октября; покупка 14 900 ₽ → `shortfall`, ждать «Подработку» 10 октября; 3 000 ₽ → `wait` (до стипендии); 500 ₽ → `ok` (лимит 420 ₽). Пять ошибок в расчётах описаны в #12 (@ruina696), в core они исправляются.

- **SF2. Демо-данные.** `data/demo/student.json` (формат `UserState`): баланс 18 430 ₽, стипендия 8 000 ₽ 5-го, подработка 25 000 ₽ 10-го, цели «Ноутбук для учёбы» (срок 01.02.2027) и «Финансовая подушка» (без срока), 25 операций за август–сентябрь. `from app.core import load_demo_state, DEMO_AS_OF` → `load_demo_state() -> UserState` (каждый раз новая копия), `DEMO_AS_OF = 2026-09-26`.

## В работе
- SF3 — расчёты нового API (`build_runway`, `check_impulse`, `build_forecast`, `build_overview`, `build_goal_plan`, `coverage_days`, `mark_recurring`).

## Заблокировано / жду от других

## Что важно знать остальным
- Импорт: `from app.core import calculate_runway, simulate, plan_goal, plan_all_goals, build_snapshot, categorize, detect_recurring, spending_breakdown, detect_risks`; `from app.ingest import import_csv`.
- Все функции чистые, дата — `today or profile.as_of or date.today()`.
- Заглушки: `spending_breakdown` — пустой `Breakdown`, `detect_risks` — `RiskReport(risks=[])`, `import_csv` — профиль без изменений и пустой отчёт, `build_snapshot` — dict с ключами `as_of, balance, next_confirmed_income, expected_incomes, payments_next_30_days, goals, missing` (деньги строками).
- `fmt_rub`: неразрывный пробел (U+00A0) между разрядами, минус — U+2212: «9 800 ₽», «785,10 ₽», «−700 ₽». Тот же формат в `formula_text` и текстах допущений — учитывайте при разборе чисел (A5 у Сони).
- `RunwayResult.balance` — баланс из профиля (без вычета покупки); покупка видна в `formula_text` и допущении `purchase`.
- Коды допущений: `horizon_default`, `income_today`, `no_payments`, `expected_income_counted`, `expected_income_ignored`, `goal_paused`, `reserve`, `delay`, `purchase`.
- `plan_goal`: `current_daily` берётся из цели с `goal_id`, иначе 0 (`projected_date=None`). Срок прошёл/сегодня → `required_daily` = вся недостающая сумма, `on_track=False`. Уже накоплено ≥ цели → `required_daily=0`, `on_track=True`, `projected_date=as_of`.
