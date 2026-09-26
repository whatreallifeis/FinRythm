# Статус: sonya

Обновляется в конце каждой задачи. Последнее обновление: 26.09.2026, A1

## Сделано
- **A1. LLMClient и FakeLLM** (`backend/app/ai/llm/`): интерфейс `LLMClient`, `ToolCall`, `LLMReply`; `FakeLLM` без сети; `get_llm(settings)` (пока только `fake`). 48 тестов в `backend/tests/ai/`.

## В работе
- A0 (доступ к LLM): ключа пока нет, работаем на `LLM_PROVIDER=fake`.
- Далее A2 — инструменты (`tools.py`, `dispatch`).

## Заблокировано / жду от других
- A2 ждёт функции core Саши (`calculate_runway`, `simulate`, `plan_goal`, `spending_breakdown`, `detect_risks`, `build_snapshot`).

## Что важно знать остальным
- **Вероника:** `from app.ai import get_llm` → `get_llm(settings)` читает `settings.llm_provider` (переменная `LLM_PROVIDER`), по умолчанию `fake`. Неизвестный провайдер → `ValueError` с понятным текстом. `answer()` появится в A3.
- История сообщений — в формате OpenAI; вызовы и результаты инструментов собираются через `assistant_message()` и `tool_message()` из `app.ai.llm`.
- FakeLLM: 1-й вызов выбирает инструмент по ключевым словам (таблица из `docs/tasks/sonya.md`, A1), 2-й — возвращает JSON `{"result","basis","assumptions","next_steps"}` только из чисел результата инструмента.
- Решения, отличные от буквы ТЗ:
  - вопросы-объяснения («что такое», «объясни»…) проверяются первыми: «что такое подписка» → `search_knowledge`, а не `detect_risks`;
  - `plan_goal` без суммы и срока вызывается с пустыми аргументами (FakeLLM не видит профиль) — первую цель пользователя подставит `dispatch` в A2;
  - год в «к 31 марта» FakeLLM берёт из даты ГГГГ-ММ-ДД в системном промпте (промпт в A3 будет её содержать).
