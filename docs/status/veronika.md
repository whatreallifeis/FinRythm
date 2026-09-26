# Статус: veronika

Обновляется в конце каждой задачи. Последнее обновление: 27.09.2026, VF1

## Сделано
- **VF0. Модели фронтенда** в `backend/app/models.py` (PR #9): `UserState`, `Operation`, `IncomeRule`, `SavingGoal`, `ImportRow`/`ImportResult`, `Explained`.
- **VF1. Хранилище и вход.** SQLite (`app.storage.Store`: сессии + `UserState` одним JSON). `POST /api/auth/demo`, `POST /api/auth/telegram` (подпись initData), дальше `Authorization: Bearer <token>`. `GET /api/health`, `GET/PUT /api/profile`, `GET /api/transactions`, `DELETE /api/dataset`. Ошибки — `{"error": {"code", "message", "field"}}` по-русски.
- **Процесс для трёх человек.** Кирилл вышел из команды. Его задачи перешли к Саше (S10–S13: демо-данные, эталон структуры трат, e2e, QA) и Соне (A9–A11: база знаний, README и документация, проверка README). Саша и Соня работают в своих ветках и вливают законченную задачу в `main` сами, без ревью.

## В работе
- VF2 — аналитика, цели, импорт, помощник, история (на заглушках до кода Саши и Сони).

## Заблокировано / жду от других

## Что важно знать остальным
<!-- изменения поведения, новые функции, которые можно использовать -->
- Указания ruina696 по бэкенду (ветка `front`) в приоритете над ТЗ и `contracts/api.md`. Где их искать — в `CLAUDE.md`.
- `frontend/`, ветку `front` и `bot/` не трогаем, пока я не скажу.
- `APP_TODAY=2026-09-26` в `.env` — демо-дата, при ней сходятся числа из `handoff.md`.
- Сериализация для фронтенда — `app.api.serialize` (`to_json`, `public_explained`): Decimal и даты в `Explained.result` можно отдавать как есть.
