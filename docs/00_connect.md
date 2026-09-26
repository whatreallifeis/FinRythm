# Как всем подключиться к репозиторию Вероники

Порядок: **Шаг 1** — все (установка, ~15 минут). **Шаг 2** — только Вероника (создание репозитория, ~15 минут). **Шаг 3** — Саша, Соня, Кирилл (подключение, ~10 минут). **Шаг 4** — все (запуск Claude Code). **Шаг 5** — ежедневная работа с git.

В командах ниже `veronika-login` — это логин Вероники на GitHub. Замените его на настоящий.

---

## Шаг 1. Установка (все четверо)

### 1.1. Аккаунт GitHub
Если нет — зарегистрируйтесь на https://github.com/signup. Отправьте свой **логин** Веронике в чат команды (она пригласит вас в репозиторий).

### 1.2. Программы

| Что | Windows (PowerShell) | macOS (Terminal) |
|---|---|---|
| Git | `winget install --id Git.Git -e` | `xcode-select --install` (или `brew install git`) |
| GitHub CLI | `winget install --id GitHub.cli -e` | `brew install gh` |
| Python 3.12 | `winget install --id Python.Python.3.12 -e` | `brew install python@3.12` |
| Claude Code | `irm https://claude.ai/install.ps1 \| iex` | `curl -fsSL https://claude.ai/install.sh \| bash` |

- Linux / WSL: Git и Python — через пакетный менеджер, GitHub CLI — по инструкции https://github.com/cli/cli#installation, Claude Code — той же командой, что для macOS.
- Если нет `brew` на macOS: https://brew.sh.
- Альтернатива для Claude Code, если установлен Node.js 18+: `npm install -g @anthropic-ai/claude-code`.
- **После установки закройте и заново откройте терминал.**

Проверка — каждая команда должна напечатать версию:
```bash
git --version
gh --version
python --version        # macOS/Linux: python3 --version — должно быть 3.12.x
claude --version
```

### 1.3. Настройка git (один раз)
```bash
git config --global user.name "Имя Фамилия"
git config --global user.email "почта-которая-на-github@example.com"
git config --global pull.rebase true
git config --global init.defaultBranch main
```

### 1.4. Вход в GitHub из терминала
```bash
gh auth login
```
Ответы: `GitHub.com` → `HTTPS` → `Yes` (authenticate Git with your GitHub credentials) → `Login with a web browser` → скопировать код, нажать Enter, вставить код в браузере, подтвердить.
Проверка: `gh auth status` → «Logged in to github.com as <ваш логин>».

### 1.5. Вход в Claude Code по подписке
```bash
claude
```
При первом запуске выберите вход **через аккаунт Claude (подписка Pro/Max)**, подтвердите в браузере. Выйти из Claude Code — `/exit` или Ctrl+C дважды.
> Важно: подписка Claude даёт доступ к Claude Code, но **не даёт API-ключ** для нашего продукта. Ключ LLM для ФинРитм — отдельно (задача A0 у Сони).

---

## Шаг 2. Вероника создаёт репозиторий

### 2.1. Залить стартовый набор
Распакуйте архив `finritm-starter.zip`, откройте терминал **в папке `finritm`** (где лежит `CLAUDE.md`):
```bash
git init -b main
git add .
git commit -m "chore: стартовый набор проекта ФинРитм"
gh repo create finritm --public --source=. --remote=origin --push
```
Репозиторий **публичный**: жюри проверяет репозиторий, а защита веток на бесплатном тарифе работает только для публичных. Секретов в наборе нет, `.env` в `.gitignore`.

Проверка: `gh repo view --web` открывает страницу репозитория с файлами.

### 2.2. Пригласить команду
Через терминал (для каждого логина):
```bash
gh api -X PUT repos/veronika-login/finritm/collaborators/ЛОГИН_САШИ -f permission=push
gh api -X PUT repos/veronika-login/finritm/collaborators/ЛОГИН_СОНИ -f permission=push
gh api -X PUT repos/veronika-login/finritm/collaborators/ЛОГИН_КИРИЛЛА -f permission=push
```
Или в браузере: репозиторий → **Settings** → **Collaborators** → **Add people** → логин → роль **Write**.

### 2.3. Метки для связи между зонами
```bash
bash scripts/setup_github.sh
```
(Windows: запустите в **Git Bash**, он установился вместе с Git.)

### 2.4. Настройки репозитория (браузер)
1. **Settings → General → Pull Requests:** оставить только **Allow squash merging**; включить **Automatically delete head branches**.
2. **Settings → Branches → Add classic branch protection rule** (или **Add branch ruleset**):
   - Branch name pattern: `main`
   - ✅ Require a pull request before merging → Required approvals: **1**
   - ✅ Require status checks to pass → добавить проверку `test` (появится в списке после первого запуска CI — если её нет, вернитесь сюда после первого PR)
   - ✅ Do not allow bypassing the above settings
   - Save.
3. **Settings → Actions → General:** Workflow permissions → **Read and write** (нужно для gitleaks) → Save.

### 2.5. Сообщить команде
В чат: ссылку `https://github.com/veronika-login/finritm` и «приглашения отправлены».

---

## Шаг 3. Саша, Соня, Кирилл подключаются

### 3.1. Принять приглашение
Письмо от GitHub → **Accept invitation**. Или откройте `https://github.com/veronika-login/finritm/invitations`.
Без принятия приглашения push не сработает (ошибка 403).

### 3.2. Склонировать
```bash
cd ~                     # или любая папка для проектов, путь БЕЗ кириллицы и пробелов
gh repo clone veronika-login/finritm
cd finritm
```

---

## Шаг 4. Окружение и запуск Claude Code (все)

### 4.1. Python-окружение
macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```
Windows (PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env
```
Если PowerShell ругается на запуск скриптов: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` и повторить активацию.

Проверка:
```bash
python contracts/reference_runway.py     # печатает эталонные числа, в т.ч. "daily_limit": "404"
pytest -q                                # пока тестов нет — «no tests ran», это нормально
git status                               # «nothing to commit, working tree clean»
```

### 4.2. Файл `.env`
- Секреты (ключ LLM, токен бота, `BOT_API_SECRET`, `TG_ID_SALT`) передаются **только личными сообщениями**, не в общий чат и не в репозиторий.
- Пока ключей нет, оставьте `LLM_PROVIDER=fake` — всё будет работать.
- Claude Code настроен **не читать** `.env` (правило в `.claude/settings.json`).

### 4.3. Запуск Claude Code
Всегда из корня репозитория, с активированным `.venv`:
```bash
claude
```
Claude Code сам прочитает `CLAUDE.md`. Первым сообщением вставьте **стартовый промпт из своего ТЗ** (`docs/tasks/<имя>.md`, раздел «Стартовый промпт»):

| Кто | Файл |
|---|---|
| Вероника | `docs/tasks/veronika.md` |
| Саша | `docs/tasks/sasha.md` |
| Соня | `docs/tasks/sonya.md` |
| Кирилл | `docs/tasks/kirill.md` |

Полезное в Claude Code:
- Разрешения на `git`, `gh`, `pytest`, `ruff`, `python` уже выданы в `.claude/settings.json`; на остальное Claude спросит — читайте, что он хочет выполнить.
- `/clear` — очистить контекст между задачами (экономит лимит подписки). После `/clear` скажите: «Продолжай по docs/tasks/<имя>.md, следующая задача — S3».
- `claude --continue` — вернуться к последнему разговору после перезапуска терминала.
- Режим планирования (Shift+Tab) — попросить сначала план, потом код. Полезно для больших задач.
- Claude **не мержит PR** — это делаете вы (Вероника) после ревью.

---

## Шаг 5. Работа с git каждый день

### Начать задачу
```bash
git switch main
git pull
git switch -c sasha/S2-runway          # <имя>/<id задачи>-<кратко>
```

### Сохранить и отправить
```bash
git add backend/app/core backend/tests/core docs/status/sasha.md     # только свои файлы
git commit -m "feat(core): расчёт дневного лимита"
git fetch origin
git rebase origin/main                 # подтянуть чужие изменения
pytest -q && ruff check .
git push -u origin HEAD
gh pr create --fill --reviewer ЛОГИН_РЕВЬЮЕРА
```
Если ветка уже была отправлена и вы сделали rebase: `git push --force-with-lease`.

### Ревью (пары: Саша ↔ Соня, Кирилл ↔ Вероника)
```bash
gh pr list                              # открытые PR
gh pr diff 12                           # посмотреть изменения PR №12
gh pr checks 12                         # статус CI
gh pr review 12 --approve               # одобрить
gh pr review 12 --request-changes -b "Что поправить"
```
Можно попросить своего Claude: «Сделай ревью PR #12: соответствие contracts/, тесты, зона файлов».

### Мерж (Вероника)
```bash
gh pr merge 12 --squash --delete-branch
```
(Claude Code мержить запрещено — это делает человек.)

### Запросы в другие зоны
```bash
gh issue list --label to:sasha --state open                       # мои входящие (подставьте себя)
gh issue create --label to:sonya --title "Нужен ..." --body "Что, зачем, пример"
gh issue close 7 --comment "Сделано в PR #15"
```

---

## Если что-то не работает

| Проблема | Решение |
|---|---|
| `remote: Permission denied` / 403 при push | Не принято приглашение (шаг 3.1) или `gh auth login` под другим аккаунтом (`gh auth status`) |
| `protected branch hook declined` | Вы пушите в `main`. Создайте ветку: `git switch -c <имя>/<задача>` и пушьте её |
| Конфликт при `git rebase` | `git status` покажет файлы. Свои — исправить, `git add <файл>`, `git rebase --continue`. Чужие — `git rebase --abort` и написать владельцу |
| `ModuleNotFoundError: app` | Запускайте из корня репозитория; для uvicorn указывайте `--app-dir backend`; pytest сам берёт пути из `pyproject.toml` |
| `python` не найден (Windows) | Переустановите Python с галочкой «Add to PATH» или используйте `py -3.12` |
| Claude Code просит войти снова | `claude` → `/login` |
| Кончился лимит подписки Claude | Сообщите в чат; задача переходит по правилам `docs/02_workflow.md` §7 |
| CI красный из-за `expected_results.json` | Кто-то правил эталон вручную. Верните файл: `git checkout origin/main -- contracts/expected_results.json` |
