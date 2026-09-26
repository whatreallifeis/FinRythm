# Кира — фронтенд

**Роль:** сайт и Telegram Mini App: экраны, взаимодействие с API, понятность для пользователя и жюри.
**Задачи:** Кира ставит себе сама. Этот файл — только зона, правила и запуск; список задач сюда не пишем.
**Зона:** ветка `front` — `frontend/`, `docs/ai-scenarios.md`, `handoff.md`; свой `docs/status/kira.md` (в `main`).
**Ревью:** не нужно. Ветка задачи — от `front` (`kira/<id>-<кратко>`), закончила — сама вливаешь в `front` (порядок — в `CLAUDE.md`).
**Ты используешь:** API из `main` — `contracts/api.md`, Swagger `/docs` на стенде.
**Тобой пользуются:** все — фронтенд собирается на стенд из `origin/front`.

## Стартовый промпт для Claude Code

```
Я Кира (ruina696). Ты работаешь на меня в проекте ФинРитм, моя зона — фронтенд в ветке front.
Сначала: git fetch origin && git checkout front && git pull.
Прочитай CLAUDE.md и docs/tasks/kira.md из main (git show origin/main:CLAUDE.md, git show origin/main:docs/tasks/kira.md),
contracts/api.md из main и handoff.md.
Входящие запросы от команды: gh issue list --label to:kira --state open — покажи их мне, решаю я.
Задачу я скажу сама. Ветка задачи — от front, вливать в front, без ревью.
После задачи: npm run build зелёный, обновить docs/status/kira.md в main отдельным маленьким PR.
Меняй только frontend/ и свои документы в ветке front. Бэкенд (backend/ в ветке front) не трогать.
```

## Как запустить фронт с настоящим бэкендом

```bash
# бэкенд — из main (папка репозитория на ветке main)
APP_TODAY=2026-09-26 uvicorn app.main:app --reload --app-dir backend        # http://localhost:8000/docs
# фронтенд — ветка front
cd frontend && printf 'VITE_API_URL=http://localhost:8000\n' > .env.local && npm ci && npm run dev
```

Моков больше нет (#62): все запросы идут в API. Стенд: https://finrhythm.ru (пароль — у Вероники).
