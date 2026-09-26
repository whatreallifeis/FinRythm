"""Сценарии помощника без LLM. Функции Саши (SF3) подменяются: числа — из сценария handoff.md."""

import datetime as dt
from decimal import Decimal

import app.core
import pytest
from app.ai import ask, scenarios
from app.core import DEMO_AS_OF, load_demo_state
from app.models import CalcStep, DataQuality, Explained, UserState

NB = "\u00a0"
AS_OF = DEMO_AS_OF


def explained(result: dict, *, sufficient: bool = True, missing=(), calc_label: str = "шаг") -> Explained:
    return Explained(
        result=result,
        assumptions=[f"допущение core: {calc_label}"],
        calculation=[CalcStep(label=calc_label, formula="из core", value=Decimal(1))],
        limitations=["ограничение core"],
        data_quality=DataQuality(sufficient=sufficient, missing=list(missing), coverage_days=57),
    )


STIPEND = {"date": "2026-10-05", "title": "Стипендия", "amount": Decimal(8000), "daysUntil": 9}
JOB = {"date": "2026-10-10", "title": "Подработка", "amount": Decimal(25000), "daysUntil": 14}


def impulse_result(amount: Decimal) -> dict:
    base = {
        "amount": amount,
        "todaySafeSpendBefore": Decimal(475),
        "redDaysBefore": 0,
        "goalImpact": None,
        "daysAfter": [],
        "hint": "",
    }
    if amount <= 500:
        return base | {
            "verdict": "ok",
            "todaySafeSpendAfter": Decimal(420),
            "redDaysAfter": 0,
            "lowestBalanceAfter": Decimal(1930),
            "waitUntil": None,
        }
    if amount <= 3000:
        return base | {
            "verdict": "wait",
            "todaySafeSpendAfter": Decimal(142),
            "redDaysAfter": 2,
            "lowestBalanceAfter": Decimal(-570),
            "waitUntil": STIPEND,
            "goalImpact": {"goalTitle": "Ноутбук для учёбы", "delayDays": 12},
        }
    return base | {
        "verdict": "shortfall",
        "todaySafeSpendAfter": Decimal(0),
        "redDaysAfter": 9,
        "lowestBalanceAfter": Decimal(-12470),
        "waitUntil": JOB,
    }


class FakeCore:
    """Подмена функций SF3 в app.core с записью вызовов."""

    def __init__(self, monkeypatch):
        self.calls: list[tuple] = []
        self.overrides: dict[str, Explained] = {}
        for name in ("build_runway", "check_impulse", "build_forecast", "build_overview", "build_goal_plan"):
            monkeypatch.setattr(app.core, name, self._make(name), raising=False)
        monkeypatch.setattr(app.core, "coverage_days", lambda ops, as_of: 57, raising=False)

    def _make(self, name):
        def fn(*args):
            self.calls.append((name, *args[1:]))
            if name in self.overrides:
                return self.overrides[name]
            return getattr(self, name)(*args)

        return fn

    def check_impulse(self, state, amount, as_of):
        return explained(impulse_result(amount), calc_label="Лимит в день после покупки")

    def build_runway(self, state, as_of):
        return explained(
            {
                "nextIncome": STIPEND,
                "todaySafeSpend": Decimal(475),
                "redDays": 0,
                "lowestBalance": Decimal(4275),
            },
            calc_label="Лимит до поступления",
        )

    def build_forecast(self, state, as_of):
        return explained(
            {
                "daysLeft": 4,
                "expectedIncome": Decimal(0),
                "plannedExpenses": Decimal(0),
                "projectedBalance": Decimal(18430),
                "safeDailySpend": Decimal(475),
                "verdict": "tight",
            },
            calc_label="Можно тратить в день до конца месяца",
        )

    def build_overview(self, state, as_of):
        return explained(
            {
                "periodFrom": "2026-09-01",
                "periodTo": "2026-09-26",
                "totalIncome": Decimal(33000),
                "totalExpense": Decimal(41500),
                "recurringTotal": Decimal(14148),
                "byCategory": [
                    {
                        "category": "rent",
                        "amount": Decimal(12000),
                        "share": Decimal("0.289"),
                        "deltaPercent": None,
                    },
                    {
                        "category": "food",
                        "amount": Decimal(6760),
                        "share": Decimal("0.163"),
                        "deltaPercent": None,
                    },
                    {
                        "category": "entertainment",
                        "amount": Decimal(5200),
                        "share": Decimal("0.125"),
                        "deltaPercent": None,
                    },
                ],
                "anomalies": [
                    {"transactionId": "t-911", "reason": "Концертные билеты — 4 800 ₽, втрое выше обычного"}
                ],
            },
            calc_label="Расходы за период",
        )

    def build_goal_plan(self, state, goal_id, as_of):
        return explained(
            {
                "goalId": goal_id,
                "monthlyPace": Decimal(13500),
                "etaMonths": 4,
                "etaDate": "2027-02-01",
                "blockers": [],
            },
            calc_label="На цель в месяц",
        )

    def called(self, name: str) -> list[tuple]:
        return [c for c in self.calls if c[0] == name]


@pytest.fixture
def core(monkeypatch) -> FakeCore:
    return FakeCore(monkeypatch)


@pytest.fixture
def demo() -> UserState:
    return load_demo_state()


class FakeKB:
    def __init__(self, fragments):
        self.fragments = fragments
        self.queries = []

    def search(self, query, k=3):
        self.queries.append(query)
        q = query.casefold()
        return [f for f in self.fragments if any(key in q for key in f["keywords"])][:k]


INFLATION = {
    "id": "kb-001",
    "title": "Инфляция",
    "text": "Инфляция — это рост цен: на ту же сумму со временем можно купить меньше.",
    "keywords": ["инфляц"],
    "source_title": "Банк России",
    "url": "https://www.cbr.ru/dkp/about_inflation/",
    "checked_at": "2026-09-26",
    "mistake": "Путать подорожание одного товара с инфляцией в целом.",
}
DEPOSIT = INFLATION | {
    "id": "kb-002",
    "title": "Вклад",
    "text": "Вклад — деньги, которые вы отдаёте банку на срок под процент.",
    "keywords": ["вклад", "депозит"],
    "url": "https://www.cbr.ru/faq/w_fin_sector/",
    "mistake": None,
}
CREDIT_HISTORY = INFLATION | {
    "id": "kb-003",
    "title": "Кредитная история",
    "text": "Кредитная история — сведения о том, как человек брал и возвращал займы.",
    "keywords": ["кредитная истори"],
    "url": "https://www.cbr.ru/ckki/",
    "mistake": None,
}
KB = FakeKB([INFLATION, DEPOSIT, CREDIT_HISTORY])


async def run(question: str, scenario: str, state: UserState, kb=None) -> Explained:
    return await ask(question, scenario, state, AS_OF, llm=None, kb=kb)


# ---------------------------------------------------------------- impulse


@pytest.mark.parametrize(
    ("question", "amount", "fragments"),
    [
        ("Хочу купить наушники за 500 ₽", Decimal(500), ["влезает", "станет 420 ₽ вместо 475 ₽"]),
        (
            "Можно сегодня потратить 3к на кроссовки?",
            Decimal(3000),
            ["лучше отложить", "с 475 ₽ до 142 ₽", "«Стипендия» 5 октября", "через 9 дней", "на 12 дней"],
        ),
        (
            "Куплю телефон за 14 900 ₽. Можно сегодня?",
            Decimal(14900),
            ["не влезает", f"до −12{NB}470 ₽", "«Подработка» 10 октября"],
        ),
    ],
)
async def test_impulse_verdicts(core, demo, question, amount, fragments):
    res = await run(question, "impulse", demo)
    assert core.called("check_impulse") == [("check_impulse", amount, AS_OF)]
    assert res.data_quality.sufficient
    for fragment in fragments:
        assert fragment in res.result["text"]


async def test_impulse_passes_core_explanation_as_is(core, demo):
    res = await run("Купить за 500 ₽?", "impulse", demo)
    assert [s.label for s in res.calculation] == ["Лимит в день после покупки"]
    assert res.assumptions == ["допущение core: Лимит в день после покупки"]
    assert res.limitations == ["ограничение core"]
    assert res.data_quality.coverage_days == 57


async def test_impulse_without_amount(core, demo):
    res = await run("Можно мне сегодня что-нибудь купить?", "impulse", demo)
    assert not res.data_quality.sufficient
    assert res.data_quality.missing == [scenarios.MISSING_AMOUNT]
    assert res.result == {"text": ""}
    assert core.called("check_impulse") == []


async def test_impulse_without_balance(core, demo):
    res = await run("Купить за 500 ₽?", "impulse", demo.model_copy(update={"balance": None}))
    assert res.data_quality.missing == [scenarios.MISSING_BALANCE]


async def test_impulse_core_says_insufficient(core, demo):
    core.overrides["check_impulse"] = explained({}, sufficient=False, missing=["поступления с датами"])
    res = await run("Купить за 500 ₽?", "impulse", demo)
    assert not res.data_quality.sufficient
    assert res.data_quality.missing == ["поступления с датами"]
    assert res.result == {"text": ""}


async def test_core_function_not_ready(monkeypatch, demo):
    monkeypatch.delattr(app.core, "check_impulse", raising=False)
    res = await run("Купить за 500 ₽?", "impulse", demo)
    assert res.data_quality.missing == [scenarios.MISSING_CORE]


# ---------------------------------------------------------------- budget


@pytest.mark.parametrize(
    "question",
    [
        "Стипендия 8 000 ₽ 5-го, подработка 25 000 ₽ 10-го. Хочу накопить на ноутбук к февралю.",
        "Составь мне бюджет на месяц",
        "Как мне дожить до стипендии и не забыть про цель?",
    ],
)
async def test_budget(core, demo, question):
    res = await run(question, "budget", demo)
    text = res.result["text"]
    assert res.data_quality.sufficient
    assert "около 475 ₽ в день" in text
    assert f"останется примерно 18{NB}430 ₽" in text
    assert "Запас небольшой" in text
    assert "До поступления «Стипендия» 9 дней" in text
    assert f"«Ноутбук для учёбы» откладывайте около 13{NB}500 ₽ в месяц" in text
    assert "1 февраля 2027 года" in text
    # план цели — только для цели со сроком
    assert core.called("build_goal_plan") == [("build_goal_plan", "g-1", AS_OF)]
    assert [s.label for s in res.calculation] == [
        "Можно тратить в день до конца месяца",
        "Лимит до поступления",
        "На цель в месяц",
    ]


@pytest.mark.parametrize(
    ("update", "missing"),
    [
        ({"balance": None}, [scenarios.MISSING_BALANCE]),
        ({"incomes": []}, [scenarios.MISSING_INCOME]),
        ({"transactions": []}, [scenarios.MISSING_PAYMENTS]),
        (
            {"balance": None, "incomes": [], "transactions": []},
            [scenarios.MISSING_BALANCE, scenarios.MISSING_INCOME, scenarios.MISSING_PAYMENTS],
        ),
    ],
)
async def test_budget_missing_data(core, demo, update, missing):
    res = await run("Составь бюджет", "budget", demo.model_copy(update=update))
    assert not res.data_quality.sufficient
    assert res.data_quality.missing == missing
    assert core.called("build_forecast") == []


async def test_budget_without_goals(core, demo):
    res = await run("Составь бюджет", "budget", demo.model_copy(update={"goals": []}))
    assert "Цель накопления не задана" in res.assumptions[-1]
    assert "На цель" not in res.result["text"]


async def test_budget_core_insufficient(core, demo):
    core.overrides["build_forecast"] = explained({}, sufficient=False, missing=["операции за текущий месяц"])
    res = await run("Составь бюджет", "budget", demo)
    assert res.data_quality.missing == ["операции за текущий месяц"]


# ---------------------------------------------------------------- expenses


@pytest.mark.parametrize(
    "question",
    [
        "Посмотри сентябрь. Обязательными считаю аренду, связь и проездной.",
        "Куда уходят мои деньги?",
        "Кажется, я много трачу на доставку еды",
    ],
)
async def test_expenses(core, demo, question):
    res = await run(question, "expenses", demo)
    text = res.result["text"]
    assert f"С 1 сентября по 26 сентября расходы — 41{NB}500 ₽" in text
    assert f"регулярные платежи — 14{NB}148 ₽" in text
    assert f"Жильё — 12{NB}000 ₽ (29%)" in text
    assert f"Еда — 6{NB}760 ₽ (16%)" in text
    assert "Концертные билеты" in text
    assert "необязательные статьи — еда, развлечения" in text
    assert [s.label for s in res.calculation] == ["Расходы за период"]


async def test_expenses_without_operations(core, demo):
    res = await run("Куда уходят деньги?", "expenses", demo.model_copy(update={"transactions": []}))
    assert res.data_quality.missing == [scenarios.MISSING_OPERATIONS]
    assert core.called("build_overview") == []


async def test_expenses_no_operations_in_period(core, demo):
    core.overrides["build_overview"] = explained({}, sufficient=False, missing=["операции за текущий месяц"])
    res = await run("Куда уходят деньги?", "expenses", demo)
    assert not res.data_quality.sufficient
    assert res.data_quality.missing == ["операции за текущий месяц"]


# ---------------------------------------------------------------- glossary


@pytest.mark.parametrize(
    ("question", "url", "fragment"),
    [
        ("Что такое инфляция? Увидела в новостях", "https://www.cbr.ru/dkp/about_inflation/", "рост цен"),
        ("Объясни, что такое вклад", "https://www.cbr.ru/faq/w_fin_sector/", "под процент"),
        ("Что значит кредитная история?", "https://www.cbr.ru/ckki/", "возвращал займы"),
    ],
)
async def test_glossary(core, demo, question, url, fragment):
    res = await run(question, "glossary", demo, kb=KB)
    assert res.data_quality.sufficient
    assert fragment in res.result["text"]
    assert [s.url for s in res.sources] == [url]


async def test_glossary_adds_typical_mistake(core, demo):
    res = await run("Что такое инфляция?", "glossary", demo, kb=KB)
    assert "Типичная ошибка: Путать подорожание" in res.result["text"]
    assert res.sources[0].title == "Банк России"


@pytest.mark.parametrize("kb", [None, KB])
async def test_glossary_unknown_term(core, demo, kb):
    res = await run("Что такое дюрация облигации?", "glossary", demo, kb=kb)
    assert not res.data_quality.sufficient
    assert res.data_quality.missing == [scenarios.MISSING_TERM]
    assert res.sources == []
    assert res.result == {"text": ""}


# ---------------------------------------------------------------- free


@pytest.mark.parametrize(
    ("question", "scenario"),
    [
        ("Что такое ключевая ставка?", "glossary"),
        ("Объясни, что значит кешбэк", "glossary"),
        ("Можно купить кроссовки за 3к?", "impulse"),
        ("Хватит ли на куртку за 7 000 ₽?", "impulse"),
        ("Куда уходят мои деньги?", "expenses"),
        ("Сколько я трачу на еду?", "expenses"),
        ("Хватит ли мне денег до конца месяца?", "budget"),
        ("Хватит ли до стипендии?", "budget"),
        ("Как быстрее накопить на ноутбук?", "budget"),
        ("Привет, как дела?", None),
        ("Напиши реферат по истории", None),
    ],
)
def test_classify_free(question, scenario):
    assert scenarios.classify_free(question) == scenario


async def test_free_runs_detected_scenario(core, demo):
    res = await run("Хватит ли на наушники за 500 ₽?", "free", demo)
    assert "влезает" in res.result["text"]
    assert core.called("check_impulse")


async def test_free_asks_to_clarify(core, demo):
    res = await run("Привет, как дела?", "free", demo)
    assert not res.data_quality.sufficient
    assert res.data_quality.missing == [scenarios.MISSING_TASK]
    assert res.data_quality.coverage_days == 57


# ---------------------------------------------------------------- общие правила


async def test_texts_use_polite_you(core, demo):
    for question, scenario in [
        ("Купить за 3000 ₽?", "impulse"),
        ("Составь бюджет", "budget"),
        ("Куда уходят деньги?", "expenses"),
    ]:
        text = (await run(question, scenario, demo)).result["text"].casefold()
        assert " ты " not in f" {text} "
        assert "твой" not in text


def test_human_date():
    assert scenarios.human_date("2026-10-05") == "5 октября"
    assert scenarios.human_date(dt.date(2027, 2, 1)) == "1 февраля"


async def test_budget_skips_missing_goal_plan(core, demo):
    core.overrides["build_goal_plan"] = None
    res = await run("Составь бюджет", "budget", demo)
    assert res.data_quality.sufficient
    assert "На цель" not in res.result["text"]


async def test_same_calc_step_shown_once(core, demo):
    core.overrides["build_runway"] = core.build_forecast(demo, AS_OF)
    res = await run("Составь бюджет", "budget", demo)
    labels = [s.label for s in res.calculation]
    assert labels.count("Можно тратить в день до конца месяца") == 1
