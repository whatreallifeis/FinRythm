# CLAUDE.md — правила для всех Claude Code в проекте «ФинРитм»

Ты — один из трёх Claude Code, которые параллельно пишут этот проект. У каждого своя зона.
Остальные работают одновременно с тобой, поэтому соблюдай правила ниже строго.

## Кто есть кто

| Человек | Зона (только эти файлы ты можешь менять, если работаешь на этого человека) | Персональное ТЗ |
|---|---|---|
| Вероника (владелец репо) | `backend/app/api/`, `backend/app/storage/`, `backend/app/main.py`, `backend/app/config.py`, `backend/app/models.py`, `backend/tests/api/`, `Dockerfile`, `docker-compose.yml`, `.github/`, `requirements*.txt`, `pyproject.toml`, `.env.example`, `CLAUDE.md`, `docs/tasks/`, `docs/0*.md` | `docs/tasks/veronika.md` |
| Саша | `backend/app/core/`, `backend/app/ingest/`, `backend/tests/core/`, `backend/tests/ingest/`, `data/demo/`, `data/samples/`, `scripts/generate_demo.py`, `tests/e2e/`, `contracts/expected_breakdown.json` (PR `contract`) | `docs/tasks/sasha.md` |
| Соня | `backend/app/ai/`, `backend/tests/ai/`, `scripts/eval_ai.py`, `docs/ai_eval.md`, `data/knowledge_base/`, `README.md`, `docs/architecture.md`, `docs/limitations.md` | `docs/tasks/sonya.md` |

Каждый также ведёт свой `docs/status/<имя>.md`.

Кирилла в команде больше нет. Его задачи перераспределены на Сашу и Соню, они записаны в конце их ТЗ.

**Первым делом спроси человека, на кого ты работаешь, если это не сказано в первом сообщении.**

## Фронтенд не трогаем

`frontend/`, ветку `front` и `bot/` **не меняй, не мержи и не ребейзь**, пока Вероника прямо не скажет. Фронтенд доработаем позже.
Ветку `front` можно только читать (`git show origin/front:<путь>`): там требования к бэкенду (см. ниже).

## Приоритет: указания ruina696 по бэкенду

ruina696 (GitHub) делает фронтенд. **Её указания по бэкенду важнее** `docs/tasks/*.md`, `docs/01_project_spec.md` и `contracts/api.md`: при расхождении делай так, как пишет она.
Где их искать:

- `git show origin/front:docs/ai-scenarios.md` — сценарии помощника (`POST /api/ask`, `scenarioId`: `expenses`, `budget`, `glossary`, `impulse`, `free`), черновики промптов, обёртка `Explained<T>`;
- `git show origin/front:frontend/src/shared/api/types.ts` — какие данные ждёт фронтенд (формы ответов, названия полей, категории);
- `git show origin/front:handoff.md` и `git show origin/front:backend/app/routes.py` — какие эндпоинты фронтенд уже вызывает. Код из ветки `front` читай как спецификацию, **не мержи**: там удалены `core` и `ai` из `main`;
- issues и комментарии ruina696: `gh issue list --author ruina696 --state open`, `gh search issues --repo whatreallifeis/FinRythm --commenter ruina696`.

Если ради её указаний нужно поменять `backend/app/models.py`, `contracts/*` или API, заведи issue `to:veronika` со ссылкой на её требование.
Внутри бэкенда деньги остаются `Decimal`. Если фронтенду нужно число, переводи его только на границе API.

## Порядок работы над каждой задачей

Каждый работает **только в своей ветке**. Закончил задачу — сам вливаешь её в `main`.
Саша и Соня мержат **без ревью** Вероники и друг друга.

1. `git checkout main && git pull`
2. Прочитай свой `docs/tasks/<имя>.md` (следующая невыполненная задача) и `docs/status/*.md` остальных.
3. Проверь входящие запросы: `gh issue list --label to:<имя> --state open` и указания ruina696 (раздел выше). Блокирующие запросы — в приоритете.
4. `git checkout -b <имя>/<id>-<кратко>`
5. Сделай задачу. Сначала тест, потом код, где это разумно.
6. `ruff check . && ruff format . && pytest` — всё зелёное.
7. Обнови `docs/status/<имя>.md`.
8. `git add` только свои файлы → коммит в стиле `feat(core): ...` → `git fetch origin && git rebase origin/main` → снова `pytest` → `git push -u origin HEAD`.
9. Влей в `main`: `gh pr create --fill` → дождись зелёного CI (`gh pr checks --watch`) → `gh pr merge --squash --delete-branch`. Ревьюер не нужен.
10. Покажи человеку ссылку на PR и краткое резюме.

Если задача не закончена, не вливай её, даже частично. Незаконченная работа остаётся в своей ветке.

## Жёсткие правила

- **Не меняй файлы вне своей зоны.** Нужно изменение у другого — создай issue: `gh issue create --label to:<владелец> --title "..." --body "..."`, в теле — что нужно, зачем, пример.
- **Контракты:** `backend/app/models.py`, `contracts/*`. Изменение — только отдельным PR с меткой `contract` и описанием, кого затрагивает. Перед мержем заведи issue `to:veronika` со ссылкой на PR. Ждать ревью не нужно.
- **Деньги — только `Decimal`.** float для денег запрещён.
- **LLM никогда не считает.** Все суммы, проценты, даты считает код в `backend/app/core/`.
- **Никаких секретов в коде и коммитах.** Ключи — только в `.env` (он в `.gitignore`). Перед коммитом проверь `git diff --staged` на ключи и токены.
- **Никаких реальных персональных и банковских данных.** Только синтетика.
- Не добавляй зависимости сам — issue `to:veronika` с названием и версией пакета.
- Тексты для пользователя — по-русски, понятно, без жаргона.
- Если задача неясна или противоречит контрактам — остановись и спроси человека, не выдумывай.

## Источники правды

| Что | Где |
|---|---|
| Требования фронтенда к бэкенду (**приоритет**) | ветка `front`, см. раздел «Приоритет: указания ruina696» |
| Общее ТЗ | `docs/01_project_spec.md` |
| Процесс | `docs/02_workflow.md` |
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
docker compose up --build                               # всё вместе
```
