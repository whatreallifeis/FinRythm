# Статус: sasha

Обновляется в конце каждой задачи. Последнее обновление: 27.09.2026, SF3

## Сделано
- **S1. Заглушки core в main, можно подключать.** Все функции из `docs/tasks/sasha.md` экспортируются из `app.core` и `app.ingest`, возвращают валидные модели. `calculate_runway` пока всегда отдаёт числа P1 из `expected_results.json`.

- **S2. Дневной лимит и «что если».** `calculate_runway` и `simulate` считают по §6.1; все 9 эталонов `expected_results.json` совпадают до копейки (`backend/tests/core/test_expected_results.py`). Полный `RunwayResult`: `mandatory_items`, `next_income_title`, `assumptions`, `missing`, `formula_text`. В `core/money.py`: `to_money`, `floor_rub`, `ceil_rub`, `fmt_num`, `fmt_rub`, `days_word`.

- **S3. План цели.** `plan_goal`, `plan_all_goals` по §6.2; эталон `goal_plan.p1_laptop` совпадает (323 ₽, 18 600 ₽, 2028-05-18).

- **SF1. Эталон ветки front.** Её API прогнан на демо-данных 26.09.2026. Сценарий `handoff.md` сходится: лимит 475 ₽ в день до стипендии 5 октября; покупка 14 900 ₽ → `shortfall`, ждать «Подработку» 10 октября; 3 000 ₽ → `wait` (до стипендии); 500 ₽ → `ok` (лимит 420 ₽). Пять ошибок в расчётах описаны в #12 (@ruina696), в core они исправляются.

- **SF2. Демо-данные.** `data/demo/student.json` (формат `UserState`): баланс 18 430 ₽, стипендия 8 000 ₽ 5-го, подработка 25 000 ₽ 10-го, цели «Ноутбук для учёбы» (срок 01.02.2027) и «Финансовая подушка» (без срока), 25 операций за август–сентябрь. `from app.core import load_demo_state, DEMO_AS_OF` → `load_demo_state() -> UserState` (каждый раз новая копия), `DEMO_AS_OF = 2026-09-26`.

- **SF3. Расчёты нового API.** В `app.core` — чистые функции на `UserState`, каждая возвращает `Explained` (`result` с ключами как в `types.ts`, деньги `Decimal`, даты — строки ISO):
  `build_runway(state, as_of)`, `check_impulse(state, amount, as_of)`, `build_forecast(state, as_of)`, `build_overview(state, as_of)`, `build_goal_plan(state, goal_id, as_of)` (`None` — цели нет → 404), `coverage_days(transactions, as_of) -> int`, `mark_recurring(transactions) -> list[Operation]`.
  Лимит на день и проверка покупки считаются одним календарём (`core/runway_calendar.py`). Числа эталона SF1 совпадают до копейки, кроме исправлений из #12.

## В работе
- SF4 — импорт `app.ingest.apply_import`.

## Заблокировано / жду от других

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
