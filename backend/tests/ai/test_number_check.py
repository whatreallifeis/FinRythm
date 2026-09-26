from decimal import Decimal
from pathlib import Path

import pytest
from app.ai import ask, scenarios
from app.ai.ask import verify_numbers
from app.ai.number_check import allowed_numbers, check_numbers, extract_numbers
from app.ai.rag import load_kb
from app.core import DEMO_AS_OF, load_demo_state
from app.models import CalcStep, DataQuality, Explained

KB = load_kb(Path(__file__).resolve().parents[3] / "data" / "knowledge_base" / "kb.json")
NB = "\u00a0"


def explained(result: dict, calculation=(), assumptions=()) -> Explained:
    return Explained(
        result=result,
        calculation=list(calculation),
        assumptions=list(assumptions),
        data_quality=DataQuality(sufficient=True),
    )


LIMIT = explained(
    {"text": "ответ", "todaySafeSpend": Decimal(404), "nextIncome": {"date": "2026-10-10", "daysUntil": 14}},
    [CalcStep(label="Баланс", formula=f"9{NB}800 ₽ − 1{NB}949 ₽", value=Decimal("7851.00"))],
)


def test_extract_numbers():
    assert extract_numbers(f"лимит 9{NB}800 ₽, резерв 785,10 ₽, 18 430 и −700") == [
        Decimal(9800),
        Decimal("785.10"),
        Decimal(18430),
        Decimal(700),
    ]
    assert extract_numbers("Ноутбук2 и t-901") == []


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("Лимит 404 ₽ в день", True),
        ("Лимит 410 ₽ в день", False),
        (f"Баланс 9{NB}800 ₽", True),
        ("Баланс 9 800 ₽", True),
        ("Стипендия 10 октября, через 14 дней", True),
        ("Свободно 7 851 ₽", True),  # округление 7851.00
        ("До поступления 15 дней", False),
    ],
)
def test_check_numbers(text, ok):
    assert check_numbers(text, allowed_numbers(LIMIT))[0] is ok


def test_answer_text_itself_is_not_a_source():
    res = explained({"text": "лимит 999 ₽"})
    assert check_numbers("лимит 999 ₽", allowed_numbers(res)) == (False, [Decimal(999)])


def test_question_and_sources_are_allowed():
    res = explained({"text": ""})
    allowed = allowed_numbers(res, question="можно за 3 000 ₽?", facts=["застраховано до 1,4 млн"])
    assert check_numbers("покупка на 3 000 ₽, страховка до 1,4 млн", allowed)[0]


def test_share_as_percent():
    res = explained({"text": "", "byCategory": [{"share": Decimal("0.39")}]})
    assert check_numbers("Развлечения — 39%", allowed_numbers(res))[0]


@pytest.mark.parametrize(
    ("question", "scenario"),
    [
        ("Хочу купить телефон за 14 900 ₽", "impulse"),
        ("Можно потратить 3000?", "impulse"),
        ("Составь бюджет", "budget"),
        ("Куда уходят деньги?", "expenses"),
        ("Хватит ли мне денег до конца месяца?", "free"),
        ("Что такое страхование вкладов?", "glossary"),
        ("Что такое налог на вклады?", "glossary"),
    ],
)
def test_template_answers_pass_on_demo(question, scenario):
    reply = scenarios.run_reply(scenario, question, load_demo_state(), DEMO_AS_OF, KB)
    assert reply.explained.data_quality.sufficient
    ok, bad = verify_numbers(reply, question)
    assert ok, bad


async def test_ask_logs_bad_numbers(monkeypatch, caplog):
    def fake_run_reply(*args):
        return scenarios.Reply(explained({"text": "Лимит 999 ₽"}), [{"todaySafeSpend": 475}])

    monkeypatch.setattr(scenarios, "run_reply", fake_run_reply)
    await ask("Составь бюджет", "budget", load_demo_state(), DEMO_AS_OF)
    assert "number check failed" in caplog.text
