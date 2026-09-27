# GigaChat, полный расчёт по выписке и объединение с фронтендом

Локальные изменения (не закоммичены). Что сделано, как запустить и как проверить.

## Как устроено

```
CSV-выписка ──► ingest.csv_text ──► UserState ──► core.report.build_report ──► сводка (все числа)
 (фронтенд или   разбор, повторы,     операции,       доходы/расходы по месяцам,        │
  консоль)       регулярные доходы    регулярное,     категории, регулярные платежи,     │ report_text
                                      баланс          календарь, прогноз, цели, риски    ▼
                                                                          GigaChat отвечает на вопрос
                                                                          по сводке ──► проверка чисел,
                                                                          языка, обращения ──► ответ
```

Считает только код. Модель получает готовую сводку и объясняет её; каждое число ответа сверяется
со сводкой и вопросом. Не сошлось — модель получает подсказку и пишет заново; не вышло — шаблон
из тех же чисел. Рискованные вопросы (микрозаймы, «куда вложить») отсекаются до модели.

## Что добавлено

| Файл | Что делает |
|---|---|
| `backend/app/core/report.py` | Полная сводка: месяцы (доходы, расходы, итог, доля сбережений), текущий месяц (категории с долями и изменением к прошлому месяцу, главные получатели, крупные траты, средний расход в день), регулярные платежи и доходы (в месяц и в год, доля от дохода), календарь до поступления, прогноз до конца месяца, цели (сколько нужно, сколько остаётся, срок при текущем темпе и если урезать траты, готовый вывод), риски. `report_text` — та же сводка текстом для модели. |
| `backend/app/ingest/csv_text.py` | CSV → строки → данные пользователя: даты `ГГГГ-ММ-ДД` и `ДД.ММ.ГГ`, суммы с пробелами и запятой, разделитель `,` или `;`. Замена выписки целиком сохраняет повторы внутри файла (две поездки по 48 ₽ в один день). |
| `backend/app/core/recurring.py` | `detect_income_rules`: регулярные поступления (стипендия, зарплата, перевод от родителей). Регулярный расход теперь требует ещё и близкого числа месяца — две покупки в Steam 9 и 18 числа не подписка. |
| `backend/app/core/day.py` | День календаря: операции, обычные траты в этот день недели, остаток на конец дня, справка по регулярным операциям. |
| `backend/app/ai/analyst.py` | Помощник-аналитик для «Свой вопрос» и «Анализ трат»: GigaChat отвечает по сводке; проверки чисел, языка, обращения на «вы», служебных пометок, списков голых чисел. Если модель не справилась — короткая сводка вместо «уточните вопрос». |
| `backend/app/ai/day_note.py` | Справка по дню календаря — GigaChat переписывает шаблон, числа сверяются, иначе шаблон. |
| `backend/app/api/routes/calendar.py` | Эндпоинты, которые уже вызывает фронтенд из `frontAND` (ниже). |
| `backend/app/models.py` | `AutopaymentRule` и `UserState.autopayments` (новое поле с пустым значением по умолчанию). |
| `scripts/csv_report.py` | Консоль: CSV → все посчитанные числа текстом или JSON. |
| `scripts/check_ai_dialogs.py` | Живая проверка помощника по HTTP на четырёх готовых выписках, отчёт в markdown. |
| `frontend/.env.backend` | Режим фронтенда «настоящий API» (`npm run dev -- --mode backend`). |

Новые эндпоинты:

```
GET    /api/calendar/{date}         -> Explained<DayInsight>   (справка — от GigaChat, если он подключён)
PUT    /api/dataset                 {rows[], balance} -> ImportResult   (замена всех данных)
PATCH  /api/transactions/{id}       {merchant} -> Transaction  (регулярную — всей серией)
POST   /api/autopayments            {title, amount, dayOfMonth, category} -> Autopayment
PATCH  /api/autopayments/{id}       {title} -> Autopayment
DELETE /api/autopayments/{id}       -> 204
PATCH  /api/incomes/{id}            {title} -> Income
GET    /api/profile                 -> + autopayments[]
```

## Запуск локально

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt -r requirements-dev.txt
# .env: LLM_PROVIDER=gigachat, GIGACHAT_CREDENTIALS=<ключ авторизации>, CORS_ORIGINS=...,http://localhost:5174
.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8001
npm --prefix frontend run dev -- --mode backend --port 5174
```

Сайт — http://localhost:5174, вкладка «Данные» → готовая выписка. Порт 8001, потому что 8000 занят
другим локальным uvicorn.

## Проверка

```bash
.venv/Scripts/python -m pytest -q                                   # 618 тестов
.venv/Scripts/python scripts/csv_report.py frontend/src/features/import/presets/worker.csv --balance 21000
.venv/Scripts/python scripts/check_ai_dialogs.py --api http://localhost:8001 --out docs/ai_live_check.md
```

Результат живой проверки — `docs/ai_live_check.md`.

Известное:
- `test_root_redirects_to_docs` падает, пока собран `frontend/dist`: тогда `/` отдаёт сайт, а не `/docs`.
- e2e-тест `test_ask_numbers_come_from_core` рассчитан на `LLM_PROVIDER=fake`: живая модель может
  не повторить в ответе «Можно купить?» название поступления. С `fake` проходят все 48 e2e.
- Шаблон «Бюджет до конца месяца» (не менялся) пишет «можно тратить 584 ₽ в день, к последнему числу
  останется примерно 4 092 ₽» — второе число без учёта дневных трат; это стоит поправить в `ai/scenarios.py`.
