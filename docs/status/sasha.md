# Статус: sasha

Обновляется в конце каждой задачи. Последнее обновление: 27.09.2026, S1

## Сделано
- **S1. Заглушки core в main, можно подключать.** Все функции из `docs/tasks/sasha.md` экспортируются из `app.core` и `app.ingest`, возвращают валидные модели. `calculate_runway` пока всегда отдаёт числа P1 из `expected_results.json`.

## В работе
- S2 — дневной лимит и «что если» по эталону.

## Заблокировано / жду от других

## Что важно знать остальным
- Импорт: `from app.core import calculate_runway, simulate, plan_goal, plan_all_goals, build_snapshot, categorize, detect_recurring, spending_breakdown, detect_risks`; `from app.ingest import import_csv`.
- Все функции чистые, дата — `today or profile.as_of or date.today()`.
- Заглушки: `spending_breakdown` — пустой `Breakdown`, `detect_risks` — `RiskReport(risks=[])`, `import_csv` — профиль без изменений и пустой отчёт, `build_snapshot` — dict с ключами `as_of, balance, next_confirmed_income, expected_incomes, payments_next_30_days, goals, missing` (деньги строками).
