# Статус: sonya

Обновляется в конце каждой задачи. Последнее обновление: 27.09.2026, AF2

## Сделано
- **A1. LLMClient и FakeLLM** (`backend/app/ai/llm/`): интерфейс `LLMClient`, `ToolCall`, `LLMReply`; `FakeLLM` без сети; `get_llm(settings)` (пока только `fake`). 48 тестов в `backend/tests/ai/`.
- **A2. Инструменты** (`backend/app/ai/tools.py`): схемы из `contracts/tools.schema.json` (`tool_schemas()`, `openai_tools()` — формат function calling), `dispatch(name, args, profile, *, kb=None) -> dict` поверх `app.core`. Ошибки аргументов → `{"error": "..."}` по-русски, без исключений. Проверено вместе с FakeLLM: вопрос → инструмент → ответ с числами из core (404 → 211 ₽).

- **AF1. Точка входа `ask()` для `POST /api/ask` (заглушка).** `from app.ai import ask`; `await ask(question, scenario_id, state, as_of, *, llm, kb) -> Explained`. Пока всегда `sufficient=False`, сценарии — в AF2.

- **AF2. Сценарии без LLM** (`app/ai/scenarios.py`): `impulse`, `budget`, `expenses`, `glossary`, `free` — текст на «вы» по шаблону из чисел `Explained` Саши; `assumptions`, `calculation`, `limitations`, `data_quality` переносятся из core без пересчёта. У каждого сценария — ветка нехватки данных (`sufficient=False` + `missing`). Проверено на настоящих расчётах SF3 и демо-профиле: 14 900 ₽ → подождать «Подработку» 10 октября, 3 000 ₽ → подождать стипендию, 500 ₽ → лимит 420 ₽, бюджет — 475 ₽ в день. Сумма из вопроса — `app/ai/amounts.py` («3к», «14 900 ₽», «2,5 тыс»; годы и дни не путает с суммой).

## В работе
- A0 (доступ к LLM): ключа пока нет, работаем на `LLM_PROVIDER=fake`.
- AF3 — фильтр рискованных запросов.

## Заблокировано / жду от других
- `glossary` работает, только когда API передаёт базу знаний (`kb`) — она появится в AF4.
- Реальные числа `plan_goal`, `spending_breakdown`, `detect_risks`, `build_snapshot` появятся с задачами Саши S3–S8 (сейчас заглушки); `calculate_runway`/`simulate` уже настоящие (S2).

## Что важно знать остальным
- **Вероника:** `from app.ai import get_llm` → `get_llm(settings)` читает `settings.llm_provider` (переменная `LLM_PROVIDER`), по умолчанию `fake`. Неизвестный провайдер → `ValueError` с понятным текстом. `answer()` появится в A3.
- История сообщений — в формате OpenAI; вызовы и результаты инструментов собираются через `assistant_message()` и `tool_message()` из `app.ai.llm`.
- FakeLLM: 1-й вызов выбирает инструмент по ключевым словам (таблица из `docs/tasks/sonya.md`, A1), 2-й — возвращает JSON `{"result","basis","assumptions","next_steps"}` только из чисел результата инструмента.
- Решения, отличные от буквы ТЗ:
  - вопросы-объяснения («что такое», «объясни»…) проверяются первыми: «что такое подписка» → `search_knowledge`, а не `detect_risks`;
  - `plan_goal` без суммы и срока вызывается с пустыми аргументами (FakeLLM не видит профиль) — первую цель пользователя подставит `dispatch` в A2;
  - год в «к 31 марта» FakeLLM берёт из даты ГГГГ-ММ-ДД в системном промпте (промпт в A3 будет её содержать).
- `dispatch`: `plan_goal` без аргументов → первая цель пользователя; `calculate_runway(count_expected_income=true)` → `k=0.5`; `spending_breakdown` без операций → `{"error": ...}` с подсказкой загрузить CSV; `search_knowledge` без базы → `{"query", "results": []}`.
- **Вероника:** `ask()` — async, возвращает `app.models.Explained` с `result={"text": ...}` (snake_case, Decimal; в camelCase переводит API). Неизвестный `scenario_id` → `ValueError`. `llm` и `kb` — те же объекты, что создаются при старте (`get_llm(settings)`, база знаний появится в AF4); можно передавать `None`.
