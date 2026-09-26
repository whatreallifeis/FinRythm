# CLAUDE.md — правила для всех Claude Code в проекте «ФинРитм»

Ты — один из четырёх Claude Code, которые параллельно пишут этот проект. У каждого своя зона.
Остальные работают одновременно с тобой, поэтому соблюдай правила ниже строго.

## Кто есть кто

| Человек | Зона (только эти файлы ты можешь менять, если работаешь на этого человека) | Персональное ТЗ |
|---|---|---|
| Вероника (владелец репо) | `backend/app/api/`, `backend/app/storage/`, `backend/app/main.py`, `backend/app/config.py`, `backend/app/models.py`, `backend/tests/api/`, `Dockerfile`, `docker-compose.yml`, `.github/`, `requirements*.txt`, `pyproject.toml`, `.env.example`, `CLAUDE.md` | `docs/tasks/veronika.md` |
| Саша | `backend/app/core/`, `backend/app/ingest/`, `backend/tests/core/`, `backend/tests/ingest/` | `docs/tasks/sasha.md` |
| Соня | `backend/app/ai/`, `backend/tests/ai/`, `scripts/eval_ai.py`, `docs/ai_eval.md` | `docs/tasks/sonya.md` |
| Кирилл | `bot/`, `data/`, `scripts/generate_demo.py`, `tests/e2e/`, `README.md`, `docs/architecture.md`, `docs/limitations.md`, `contracts/expected_breakdown.json` | `docs/tasks/kirill.md` |

Каждый также ведёт свой `docs/status/<имя>.md`.

**Первым делом спроси человека, на кого ты работаешь, если это не сказано в первом сообщении.**

## Порядок работы над каждой задачей

1. `git checkout main && git pull`
2. Прочитай свой `docs/tasks/<имя>.md` (следующая невыполненная задача) и `docs/status/*.md` остальных.
3. Проверь входящие запросы: `gh issue list --label to:<имя> --state open`. Блокирующие запросы — в приоритете.
4. `git checkout -b <имя>/<id>-<кратко>`
5. Сделай задачу. Сначала тест, потом код, где это разумно.
6. `ruff check . && ruff format . && pytest` — всё зелёное.
7. Обнови `docs/status/<имя>.md`.
8. `git add` только свои файлы → коммит в стиле `feat(core): ...` → `git fetch origin && git rebase origin/main` → `git push -u origin HEAD` → `gh pr create --fill --reviewer <ревьюер>`.
9. Покажи человеку ссылку на PR и краткое резюме. **Не мержи сам.**

Ревьюеры: Саша ↔ Соня, Кирилл ↔ Вероника. PR с меткой `contract` — всегда Вероника.

## Жёсткие правила

- **Не меняй файлы вне своей зоны.** Нужно изменение у другого — создай issue: `gh issue create --label to:<владелец> --title "..." --body "..."`, в теле — что нужно, зачем, пример.
- **Контракты неприкосновенны:** `backend/app/models.py`, `contracts/*`. Изменение — только отдельным PR с меткой `contract` и описанием, кого затрагивает.
- **Деньги — только `Decimal`.** float для денег запрещён. В JSON деньги — строки.
- **LLM никогда не считает.** Все суммы, проценты, даты считает код в `backend/app/core/`.
- **Никаких секретов в коде и коммитах.** Ключи — только в `.env` (он в `.gitignore`). Перед коммитом проверь `git diff --staged` на ключи и токены.
- **Никаких реальных персональных и банковских данных.** Только синтетика.
- Не добавляй зависимости сам — issue `to:veronika` с названием и версией пакета.
- Тексты для пользователя — по-русски, понятно, без жаргона.
- Если задача неясна или противоречит контрактам — остановись и спроси человека, не выдумывай.

## Источники правды

| Что | Где |
|---|---|
| Общее ТЗ | `docs/01_project_spec.md` |
| Процесс, таймлайн, синхронизации | `docs/02_workflow.md` |
| Модели данных | `backend/app/models.py` |
| API | `contracts/api.md` |
| CSV, категории, база знаний, демо-данные | `contracts/data_formats.md` |
| Инструменты для LLM | `contracts/tools.schema.json` |
| Эталонные числа | `contracts/expected_results.json` ← `contracts/reference_runway.py` |

## Команды

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                                    # заполнить секреты, НЕ коммитить
uvicorn app.main:app --reload --app-dir backend         # API на http://localhost:8000/docs
pytest                                                  # все тесты
pytest backend/tests/core -q                            # тесты одной зоны
ruff check . && ruff format .
python contracts/reference_runway.py                    # пересчитать эталон (не менять вручную)
python -m bot                                           # запустить бота (нужен TELEGRAM_BOT_TOKEN)
docker compose up --build                               # всё вместе
```
