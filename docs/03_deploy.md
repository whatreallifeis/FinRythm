# Тестовый стенд на сервере Рег.облака

Цель — вручную проверить фронтенд и бэкенд вместе, на одном адресе по HTTPS, не открывая стенд всему интернету.

```
браузер ──HTTPS──► caddy (80/443, пароль на сайт) ──► /        → собранный фронтенд из ветки front
                                                   ├─► /api/*  → api (FastAPI, SQLite в томе Docker)
                                                   └─► /docs   → Swagger API
                   Алиса AI (Yandex AI Studio, HTTPS) ◄── api   (модель помощника, по ключу из .env)
```

- Фронтенд собирается из `origin/front` без правок кода; моков в нём нет, все запросы идут в API.
- Наружу открыты только 80 и 443. API доступен только внутри Docker.
- Сайт и Swagger закрыты паролем (basic auth). `/api/*` без пароля: там свой токен сессии.
- Всё, что описано здесь, проверяет CI (job `deploy`): сборка фронтенда, стенд целиком, пароль, сценарий «демо → календарь».

Время на первый запуск — около 30 минут.

---

## 1. Сервер

В Рег.облаке создайте облачный сервер:

| Что | Значение |
|---|---|
| Образ | Ubuntu 24.04 |
| vCPU / RAM | 2 / 2–4 ГБ (модель работает в Yandex AI Studio, не на сервере) |
| Диск | 20 ГБ |

При создании добавьте свой **публичный SSH-ключ** (вход по паролю не нужен). Если ключа нет — на своём компьютере:
`ssh-keygen -t ed25519`, публичная часть — в `~/.ssh/id_ed25519.pub`.

Запишите публичный IP сервера, дальше он — `IP`.

## 2. Базовая безопасность (один раз)

```bash
ssh root@IP

adduser finritm                               # пароль нужен только для sudo
usermod -aG sudo finritm
rsync -a ~/.ssh /home/finritm/ && chown -R finritm:finritm /home/finritm/.ssh

# вход только по ключу и не под root
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/; s/^#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart ssh

# фаервол: только SSH и веб
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443 && ufw --force enable

# автоматические обновления безопасности
apt update && apt install -y unattended-upgrades git

exit
```

Дальше — всегда `ssh finritm@IP`.

> Docker открывает опубликованные порты в обход ufw. Поэтому в `deploy/compose.yml` наружу опубликованы только 80 и 443 у caddy, а у api портов нет. Не добавляйте ему `ports:`.

## 3. Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker finritm
exit            # перезайти, чтобы группа docker применилась
ssh finritm@IP
docker run --rm hello-world
```

## 4. Код на сервере

Репозиторий приватный. Даём серверу доступ **только на чтение** через deploy key:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/finritm_deploy -N "" -C "finritm-server"
cat ~/.ssh/finritm_deploy.pub
```

GitHub → репозиторий → Settings → Deploy keys → Add deploy key: вставить ключ, **Allow write access не ставить**.

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/finritm_deploy
EOF
git clone git@github.com:whatreallifeis/FinRythm.git ~/finritm
cd ~/finritm
```

## 5. Настройки `.env`

```bash
cp .env.example .env && chmod 600 .env
docker run --rm caddy:2 caddy hash-password --plaintext 'придумайте-пароль'   # скопируйте хеш
openssl rand -hex 16                                                        # для TG_ID_SALT
nano .env
```

Заполнить:

| Переменная | Значение |
|---|---|
| `APP_ENV` | `prod` |
| `APP_TODAY` | `2026-09-26` — на эту дату рассчитан демо-сценарий. Пусто — настоящая дата |
| `GIT_SHA` | `dev` или короткий хеш коммита из `git rev-parse --short HEAD` — виден в `/api/health` |
| `LLM_PROVIDER` | `fake` или Алиса AI — раздел 9 |
| `TG_ID_SALT` | вывод `openssl rand -hex 16` |
| `SITE_ADDRESS` | свой домен или IP через sslip.io: IP `203.0.113.10` → `203-0-113-10.sslip.io` |
| `BASIC_AUTH_USER` | логин для команды, например `team` |
| `BASIC_AUTH_HASH` | хеш из `caddy hash-password` **в одинарных кавычках**: `'$2a$14$...'` |

`CORS_ORIGINS` на сервере не нужен: фронтенд и API на одном адресе. Файл `.env` никуда не копируйте и не коммитьте. Пароль от сайта передавайте команде лично.

## 6. Сборка и запуск

```bash
sh deploy/build-frontend.sh                                        # фронтенд из origin/front → .deploy/frontend-dist
docker compose -f deploy/compose.yml --env-file .env up -d --build
docker compose -f deploy/compose.yml --env-file .env ps            # api и caddy — running
docker compose -f deploy/compose.yml --env-file .env logs -f caddy # дождаться «certificate obtained successfully», Ctrl+C
```

Откройте `https://SITE_ADDRESS` — браузер спросит логин и пароль из `.env`.
Проверка без браузера: `curl https://SITE_ADDRESS/api/health` → `{"status":"ok","llm_provider":"fake",...}`.

## 7. Что проверить руками

Числа — для `APP_TODAY=2026-09-26` и демо-набора.

1. **Вход.** Сайт открылся после пароля, фронтенд предлагает войти → демо-вход.
2. **Пустое состояние.** Видна только вкладка «Данные» и просьба вставить данные.
3. **Демо.** «Вставить пример» → открывается Обзор.
4. **Календарь до стипендии.** Можно тратить **475 ₽ в день**, стипендия 8 000 ₽ **5 октября** (через 9 дней), красных дней нет.
5. **«Могу купить это сегодня?»** 14 900 ₽ → «Сейчас не влезет», совет дождаться подработки **10 октября**. 500 ₽ → влезает, лимит станет **420 ₽** в день.
6. **Помощник.** Каждый сценарий (траты, бюджет, термин, покупка, свой вопрос). В ответе видны допущения, расчёт, ограничения. Рискованный вопрос («куда вложить деньги», «дай кредит») → вежливый отказ.
7. **Цели.** Создать, изменить, удалить; накоплено больше суммы цели → понятная ошибка.
8. **Импорт.** Пример из ветки front: `git show origin/front:data/sample/transactions.csv > ~/ok.csv`, `git show origin/front:data/sample/transactions-with-errors.csv > ~/bad.csv` (скачайте на свой компьютер: `scp finritm@IP:~/ok.csv .`). Хороший файл импортируется, в плохом — ошибки по строкам по-русски.
9. **Выход и чужие данные.** Второй браузер (инкогнито) — пустые данные, не видит первого пользователя.
10. **Swagger.** `https://SITE_ADDRESS/docs` → `POST /api/auth/demo` → скопировать `token` → кнопка **Authorize** → любые запросы.

Всё, что работает не так, — issue владельцу: расчёты — `to:sasha`, помощник — `to:sonya`, API и стенд — `to:veronika`, фронтенд — упомянуть @ruina696. В issue: что сделали, что ожидали, что увидели, скриншот.

## 8. Обновление, логи, сброс

```bash
cd ~/finritm && git pull
sh deploy/build-frontend.sh                                        # если менялась ветка front
docker compose -f deploy/compose.yml --env-file .env up -d --build

docker compose -f deploy/compose.yml --env-file .env logs -f api   # логи API (без текста вопросов и токенов)
docker compose -f deploy/compose.yml --env-file .env restart api
docker compose -f deploy/compose.yml --env-file .env down          # остановить (данные сохраняются)
docker volume rm finritm_finritm-data                              # стереть данные пользователей (после down)
```

`down -v` удалит и сертификаты caddy — Let's Encrypt ограничивает частые перевыпуски, без нужды не делайте.

## 9. Модель: Алиса AI (Yandex AI Studio)

Помощник работает с моделью через OpenAI-совместимый API (`LLM_PROVIDER=openai_compat`). Используем **Алису AI** — модель Яндекса `aliceai-llm` из Yandex AI Studio. Числа модель не считает: она только переписывает готовый ответ, а проверка чисел отбрасывает выдуманные. Не успела за `LLM_TIMEOUT` секунд, ответила не по-русски или с чужими числами — пользователь получает шаблонный ответ из тех же чисел, а не ошибку. Отказы на рискованные вопросы и «не хватает данных» идут без модели.

**Ключ — один раз, в консоли Yandex Cloud** (https://console.yandex.cloud; нужен платёжный аккаунт, у новых пользователей есть стартовый грант):
1. Откройте каталог (или создайте `finritm`) и скопируйте **ID каталога** — строка вида `b1g…` рядом с названием.
2. «Сервисные аккаунты» → «Создать» → имя `finritm-ai`, роль **`ai.languageModels.user`**.
3. В аккаунте → «Создать новый ключ» → **API-ключ**, область действия **`yc.ai.languageModels.execute`**. Скопируйте секрет — он показывается один раз.

**Настройки** (в `.env` на сервере или локально; ключ — только в `.env`, не в git и не в общий чат):

```
LLM_PROVIDER=openai_compat
LLM_BASE_URL=https://ai.api.cloud.yandex.net/v1
LLM_API_KEY=<API-ключ>
LLM_MODEL=gpt://<ID каталога>/aliceai-llm
OPENAI_PROJECT_ID=<ID каталога>
LLM_TIMEOUT=40
```

Затем на сервере: `docker compose -f deploy/compose.yml --env-file .env up -d api`. Проверка: `curl https://SITE_ADDRESS/api/health` → `"llm_provider":"openai_compat"`; вопрос в «Помощнике» — ответ живым текстом. Ошибки модели — в `docker compose ... logs api` (`llm error status=401` — неверный ключ или роль, `403` — нет доступа к каталогу).

Вернуться к шаблонам без модели: `LLM_PROVIDER=fake` и `up -d api`.

## 10. Проверить локально, без сервера

Быстрее всего для разработки. Нужны Python и Node 20+; для живых ответов помощника — ключ Алисы AI (раздел 9).

```bash
# бэкенд — в корне репозитория, .env как в разделе 9 или с LLM_PROVIDER=fake
uvicorn app.main:app --reload --app-dir backend                   # http://localhost:8000/docs

# фронтенд — отдельной папкой из ветки front, код не меняем
git worktree add ../FinRythm-front origin/front
cd ../FinRythm-front/frontend
printf 'VITE_API_URL=http://localhost:8000\n' > .env.local
npm ci && npm run dev                                             # http://localhost:5173
```

`CORS_ORIGINS=http://localhost:5173` уже стоит в `.env.example`.

## Чек-лист безопасности стенда

- [ ] Вход на сервер только по SSH-ключу, root-логин выключен, ufw пускает только 22/80/443.
- [ ] У api нет `ports:` в `deploy/compose.yml`.
- [ ] Ключ Алисы AI — только в `.env`; у сервисного аккаунта одна роль `ai.languageModels.user`.
- [ ] Deploy key только на чтение.
- [ ] `.env` с правами 600, не в git; пароль сайта передан лично.
- [ ] `BASIC_AUTH_HASH` задан — без пароля caddy не запустится.
- [ ] Только синтетические данные: демо-набор и файлы-примеры. Реальные выписки на стенд не загружаем.
- [ ] После защиты стенд останавливаем (`down`) или удаляем сервер.
