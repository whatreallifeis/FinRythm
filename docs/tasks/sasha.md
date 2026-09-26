# ТЗ: Саша — финансовое ядро и импорт данных

**Роль:** backend-разработчик расчётной логики. Всё, что считает деньги, — твоё.
**Зона:** `backend/app/core/`, `backend/app/ingest/`, `backend/tests/core/`, `backend/tests/ingest/`, `docs/status/sasha.md`.
**Ревьюер твоих PR:** Соня. **Ты ревьюишь:** PR Сони.
**Твоими функциями пользуются:** Соня (инструменты для LLM), Вероника (эндпоинты API), Кирилл (эталоны структуры трат, e2e).

## Стартовый промпт для Claude Code

Скопируй в `claude` после запуска в папке репозитория:

```
Я Саша. Ты работаешь на меня в проекте ФинРитм.
Прочитай CLAUDE.md, docs/01_project_spec.md (разделы 5.2 и 6), docs/tasks/sasha.md,
backend/app/models.py, contracts/reference_runway.py, contracts/expected_results.json, contracts/data_formats.md.
Затем проверь входящие issues: gh issue list --label to:sasha --state open.
Начни с задачи S1. После каждой задачи: тесты, ruff, обновить docs/status/sasha.md, PR на ревью Соне.
Меняй только файлы моей зоны. Если что-то противоречит контрактам — остановись и спроси меня.
```

## Публичный интерфейс (обязательные сигнатуры)

Все функции — чистые (без БД, сети, текущего времени внутри: дата берётся из `profile.as_of` или параметра `today`). Экспортируются из `backend/app/core/__init__.py`, чтобы другие импортировали так: `from app.core import calculate_runway`.

```python
# backend/app/core/__init__.py
from decimal import Decimal
from datetime import date
from app.models import (Profile, Transaction, RunwayResult, SimulationResult, GoalPlan,
                        Breakdown, RecurringItem, RiskReport, ImportReport)

def calculate_runway(profile: Profile, *, purchase: Decimal = Decimal(0), delay_days: int = 0,
                     k: Decimal | None = None, today: date | None = None) -> RunwayResult: ...
def simulate(profile: Profile, *, purchase: Decimal = Decimal(0), delay_days: int = 0,
             today: date | None = None) -> SimulationResult: ...
def plan_goal(profile: Profile, *, target_amount: Decimal, deadline: date, saved_amount: Decimal = Decimal(0),
              title: str = "Цель", goal_id: str | None = None, today: date | None = None) -> GoalPlan: ...
def plan_all_goals(profile: Profile, today: date | None = None) -> list[GoalPlan]: ...
def build_snapshot(profile: Profile, today: date | None = None) -> dict: ...   # для инструмента get_snapshot
def categorize(description: str, amount: Decimal) -> str: ...
def detect_recurring(transactions: list[Transaction]) -> list[RecurringItem]: ...
def spending_breakdown(profile: Profile, *, period_days: int = 30, today: date | None = None) -> Breakdown | None: ...
def detect_risks(profile: Profile, today: date | None = None) -> RiskReport: ...

# backend/app/ingest/__init__.py
def import_csv(profile: Profile, content: bytes, *, mode: Literal["append", "replace"],
               today: date | None = None) -> tuple[Profile, ImportReport]: ...
```

Правило `today`: `as_of = today or profile.as_of or date.today()`.
Если в `plan_goal` передан `goal_id` существующей цели — `current_daily` берётся из неё, иначе 0.

---

## S1. Заглушки всех функций · Ч0:45–1:15 · ПЕРВЫЙ PR, СРОЧНО

**Зачем:** Вероника и Соня подключают твои функции сразу, не дожидаясь реализации.

- Создай модули: `core/runway.py`, `core/goals.py`, `core/categories.py`, `core/recurring.py`, `core/breakdown.py`, `core/risks.py`, `core/snapshot.py`, `core/money.py` (утилиты округления и форматирования), `ingest/csv_import.py`.
- Все сигнатуры из раздела выше, экспорт через `__init__.py`.
- Заглушки возвращают **валидные объекты моделей** (не `NotImplementedError`): `calculate_runway` — значения P1 из `expected_results.json`, остальные — правдоподобные пустые результаты (`Breakdown` с пустыми списками, `RiskReport(risks=[])`, `ImportReport(added=0, ...)`).
- Тест `tests/core/test_stubs_contract.py`: каждая функция вызывается на P1 и возвращает объект нужного типа.

**Готово, когда:** PR влит, в `docs/status/sasha.md` написано «заглушки core в main, можно подключать».

## S2. Дневной лимит и «что если» · Ч1:15–2:45

- `core/money.py`: `to_money(x) -> Decimal` (2 знака, ROUND_HALF_UP), `floor_rub(x)`, `ceil_rub(x)`, `fmt_rub(x) -> "9 800 ₽"` / `"785,10 ₽"` (неразрывный пробел ` ` между разрядами, запятая для копеек, копейки не показывать, если .00).
- `core/runway.py`: реализация формулы из `docs/01_project_spec.md` §6.1. Эталон — `contracts/reference_runway.py`: повтори логику, но на моделях `Profile` и с полным `RunwayResult`:
  - `mandatory_items` — каждое повторение платежа в окне (название, сумма, дата), отсортировано по дате;
  - `next_income_title` — название поступления;
  - `assumptions` (коды и тексты по-русски):
    - `horizon_default` — «Дата следующего поступления не указана — считаем на 30 дней»;
    - `income_today` — «Поступление сегодня — считаем на 1 день»;
    - `no_payments` — «Обязательные платежи не указаны — если они есть, лимит завышен»;
    - `expected_income_counted` — «Учтено 50% ожидаемых поступлений (N ₽) — эти деньги ещё не пришли»;
    - `expected_income_ignored` — «Ожидаемые поступления (N ₽) не учтены, пока не придут» (если есть и k=0);
    - `goal_paused` — «Взнос в цель уменьшен/приостановлен: не хватает денег до поступления»;
    - `reserve` — «Отложен резерв 10% на непредвиденное»;
    - `delay` — «Сценарий: поступление задерживается на N дней»;
    - `purchase` — «Сценарий: покупка на N ₽».
  - `missing` при `balance is None`: `MissingData(field="balance", message="Укажите текущий баланс — без него лимит не посчитать")`.
  - `formula_text`:
    - ok: `"(9 800 − 1 949 обяз. − 785,10 резерв − 1 400 в цель) ÷ 14 дн. = 404 ₽ в день"`;
    - deficit: `"2 500 − 3 200 обяз. = −700 ₽: не хватает 700 ₽ до поступления"`.
- `simulate()` → `SimulationResult(before, after, delta_daily_limit = after − before)`.
- Тесты `tests/core/test_expected_results.py`: **параметризованный тест по всем ключам `contracts/expected_results.json`** — сравнение каждого поля. Плюс тесты на каждое допущение.

**Готово, когда:** все 9 эталонов совпадают до копейки; P1 `formula_text` как в примере.

## S3. План цели · Ч2:45–3:15

- `core/goals.py`: `plan_goal`, `plan_all_goals` по §6.2 спецификации.
- Граничные: `days_left ≤ 0` → `required_daily = target − saved`, допущение-подобное поведение (on_track=False); `saved ≥ target` → `required_daily = 0`, `on_track=True`, `projected_date = as_of`.
- Тест: эталон `goal_plan.p1_laptop` из `expected_results.json` (323 ₽, 18 600 ₽, 2028-05-18).

## S4. Категоризация и регулярные платежи · Ч3–4

- `core/categories.py`: словарь ключевых слов по `contracts/data_formats.md` §2 и спецификации §6.3; нормализация (нижний регистр, `ё→е`). Не меньше 60 ключевых слов. Доходы (amount > 0) → категории доходов.
- `core/recurring.py`: `detect_recurring` по §6.4.
- Тесты: 30+ примеров категоризации; регулярность на синтетических списках (месячная, недельная, нерегулярная, суммы ±5% и ±10%).

## S5. Структура расходов · Ч4–4:45

- `core/breakdown.py` по §6.4–6.5: период `[as_of − period_days, as_of)`, категории транзакций без категории — через `categorize`. Доли с 1 знаком, сумма долей = 100.0 (остаток округления добавить к крупнейшей категории). `None`, если транзакций нет.
- **Вместе с Кириллом (задача K4):** когда в `main` появятся `data/demo/p1.json` и `p3.json`, прогоните `spending_breakdown` и `detect_risks`, проверьте вручную 2–3 категории калькулятором, Кирилл сохраняет результат в `contracts/expected_breakdown.json` (PR `contract`, ты — ревьюер). Потом добавь тест на этот файл.

## S6. Импорт CSV · Ч4:45–5:45

- `ingest/csv_import.py` строго по `contracts/data_formats.md` §1: автоопределение разделителя (`,`/`;`), BOM, форматы дат, числа с пробелами и запятой, лишние колонки, дубликаты, **16 цифр подряд → отказ строки**, лимит 5 000 строк.
- Каждой новой транзакции: `id = "csv-" + sha1(date|amount|description)[:12]`, `source="csv"`, категория из файла или `categorize`.
- `mode="replace"` — заменить `transactions`, `append` — добавить без дубликатов. `origin` не трогать (ставит API).
- Тесты: корректный файл, `;`, BOM, `ДД.ММ.ГГГГ`, `-1 200,50`, пустые строки, нет колонки `amount` (ошибка всего файла), `amount=0`, дата в будущем, дубликат, номер карты в описании. Тестовые файлы — строки внутри тестов (не зависим от `data/`).
- Сообщи Веронике в issue `to:veronika`: «ingest готов, сигнатура такая-то».

## S7. Риски · Ч5:45–7

- `core/risks.py` по §6.6: подписки (из `detect_recurring` **и** из `payments` с категорией «Подписки», без двойного учёта одной подписки), аномалии, дефицит (из `calculate_runway`), дата обнуления баланса, `no_data`.
- Тексты рисков по-русски, конкретные: «Подписка на кино — 299 ₽ в месяц», «Трата „Кроссовки“ 6 990 ₽ в 4,7 раза больше обычной в категории „Одежда“».
- Тест на P3: ровно 2 подписки, `monthly_cost` в сумме 598 ₽.

## S8. Граничные случаи и полировка · Ч7–9

- `build_snapshot()` для инструмента `get_snapshot`: баланс, ближайшее подтверждённое и ожидаемые поступления, платежи в ближайшие 30 дней, цели, `missing`. Все деньги строками.
- Граничные тесты: `balance=0`; огромные суммы (10 млн); платёж ровно в день поступления (не входит в окно); `delay_days=60`; `reserve_pct=0` и `50`; `k=1`; цель с `daily_contribution=0`; несколько подтверждённых поступлений (берётся ближайшее).
- Покрытие `core` ≥ 80%: `pytest backend/tests/core --cov=app.core`.

## S9. После фриза · Ч9–11
Только исправления по issues `to:sasha` и помощь Соне, если инструменты возвращают неудобные для LLM данные.

## Критерии приёмки зоны
- [ ] Все значения `expected_results.json` и `expected_breakdown.json` проходят.
- [ ] Ни одного `float` в денежной логике (`grep -rn "float" backend/app/core backend/app/ingest` — только в комментариях или приведениях для долей, если нужно).
- [ ] Функции чистые: нет `date.today()` внутри, кроме как в значении по умолчанию через `as_of`.
- [ ] Покрытие core ≥ 80%.
