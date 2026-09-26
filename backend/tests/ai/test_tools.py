import json
from pathlib import Path

import pytest
from app.ai.llm.base import ToolCall, tool_message
from app.ai.llm.fake import FakeLLM, build_answer
from app.ai.tools import dispatch, openai_tools, tool_names
from app.models import Profile, Transaction

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"


def profile(name: str = "p1") -> Profile:
    return Profile.model_validate_json((CONTRACTS / "profiles" / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def p1() -> Profile:
    return profile("p1")


class FakeKB:
    def __init__(self, fragments: list[dict]):
        self.fragments = fragments
        self.queries: list[str] = []

    def search(self, query: str, k: int = 3) -> list[dict]:
        self.queries.append(query)
        return self.fragments[:k]


FRAGMENT = {
    "id": "kb-001",
    "title": "Финансовая подушка безопасности",
    "text": "Финансовая подушка — запас денег на случай непредвиденных ситуаций.",
    "keywords": ["подушка"],
    "source_title": "Банк России, «Финансовая культура»",
    "url": "https://fincult.info/",
    "checked_at": "2026-09-26",
}


# ---------------------------------------------------------------- схемы


def test_tool_names_match_contract():
    contract = json.loads((CONTRACTS / "tools.schema.json").read_text(encoding="utf-8"))
    assert tool_names() == [t["name"] for t in contract["tools"]]
    assert len(tool_names()) == 7


def test_openai_format():
    tools = openai_tools()
    assert all(t["type"] == "function" for t in tools)
    simulate = next(t for t in tools if t["function"]["name"] == "simulate")
    assert simulate["function"]["parameters"]["properties"]["delay_days"]["maximum"] == 60


# ---------------------------------------------------------------- каждый инструмент на P1


def test_get_snapshot(p1):
    res = dispatch("get_snapshot", {}, p1)
    assert res["as_of"] == "2026-09-26"
    assert res["balance"] == "9800.00"


def test_calculate_runway(p1):
    res = dispatch("calculate_runway", {}, p1)
    assert res["daily_limit"] == "404"
    assert res["reserve"] == "785.10"
    json.dumps(res)  # JSON-совместимо


def test_calculate_runway_with_expected_income(p1):
    res = dispatch("calculate_runway", {"count_expected_income": True}, p1)
    assert res["daily_limit"] == "547"
    assert res["expected_income_counted"] == "2000.00"


def test_simulate_purchase(p1):
    res = dispatch("simulate", {"purchase": 3000}, p1)
    assert res["before"]["daily_limit"] == "404"
    assert res["after"]["daily_limit"] == "211"
    assert res["delta_daily_limit"] == "-193"


def test_simulate_float_and_delay(p1):
    res = dispatch("simulate", {"purchase": 3000.0, "delay_days": 7}, p1)
    assert res["purchase"] == "3000.00"
    assert res["delay_days"] == 7


def test_simulate_delay(p1):
    assert dispatch("simulate", {"delay_days": 7}, p1)["after"]["daily_limit"] == "236"


def test_plan_goal_default_first_goal(p1):
    res = dispatch("plan_goal", {}, p1)
    assert res["goal_id"] == "g1"
    assert res["title"] == "Ноутбук"
    assert res["target_amount"] == "60000.00"
    assert res["deadline"] == "2027-03-31"


def test_plan_goal_by_id(p1):
    assert dispatch("plan_goal", {"goal_id": "g1"}, p1)["goal_id"] == "g1"


def test_plan_goal_new(p1):
    res = dispatch("plan_goal", {"target_amount": 20000, "deadline": "2027-01-31", "title": "Поездка"}, p1)
    assert res["goal_id"] is None
    assert res["title"] == "Поездка"
    assert res["target_amount"] == "20000.00"


def test_spending_breakdown(p1):
    p = p1.model_copy(
        update={
            "transactions": [
                Transaction(id="t1", date="2026-09-20", amount="-350", description="Пятёрочка"),
            ]
        }
    )
    res = dispatch("spending_breakdown", {"period_days": 30}, p)
    assert "error" in res or res["period_to"] == "2026-09-26"


def test_detect_risks(p1):
    assert "risks" in dispatch("detect_risks", {}, p1)


def test_search_knowledge(p1):
    kb = FakeKB([FRAGMENT])
    res = dispatch("search_knowledge", {"query": "что такое подушка"}, p1, kb=kb)
    assert kb.queries == ["что такое подушка"]
    assert res["results"][0]["url"] == "https://fincult.info/"


def test_search_knowledge_without_kb(p1):
    assert dispatch("search_knowledge", {"query": "подушка"}, p1) == {"query": "подушка", "results": []}


# ---------------------------------------------------------------- ошибки → {"error": ...}


@pytest.mark.parametrize(
    ("name", "args", "fragment"),
    [
        ("simulate", {"purchase": -5}, "отрицательным"),
        ("simulate", {"purchase": "много"}, "числом"),
        ("simulate", {"delay_days": 61}, "от 0 до 60"),
        ("simulate", {"delay_days": 1.5}, "целым"),
        ("simulate", {}, "purchase"),
        ("simulate", {"amount": 100}, "не принимает"),
        ("calculate_runway", {"count_expected_income": "да"}, "true или false"),
        ("plan_goal", {"goal_id": "nope"}, "не найдена"),
        ("plan_goal", {"target_amount": 0, "deadline": "2027-01-01"}, "больше нуля"),
        ("plan_goal", {"target_amount": 1000, "deadline": "31.03.2027"}, "ГГГГ-ММ-ДД"),
        ("plan_goal", {"target_amount": 1000}, "deadline"),
        ("spending_breakdown", {"period_days": 3}, "от 7 до 180"),
        ("search_knowledge", {}, "query"),
        ("search_knowledge", {"query": "a"}, "query"),
    ],
)
def test_bad_arguments_return_error(p1, name, args, fragment):
    res = dispatch(name, args, p1)
    assert set(res) == {"error"}
    assert fragment in res["error"]


def test_unknown_tool(p1):
    res = dispatch("transfer_money", {}, p1)
    assert "Неизвестный инструмент" in res["error"]
    assert "calculate_runway" in res["error"]


def test_arguments_not_object(p1):
    assert "error" in dispatch("simulate", [1, 2], p1)


def test_none_arguments_ok(p1):
    assert dispatch("calculate_runway", None, p1)["daily_limit"] == "404"


def test_plan_goal_without_goals_needs_amount():
    res = dispatch("plan_goal", {}, profile("p3"))
    assert "target_amount" in res["error"]


# ---------------------------------------------------------------- FakeLLM + dispatch вместе


@pytest.mark.parametrize(
    ("question", "fragment"),
    [
        ("Хочу купить кроссовки за 3000", "с 404 ₽ до 211 ₽"),
        ("Сколько я могу тратить в день?", "404 ₽ в день"),
        ("Что если стипендия задержится на неделю?", "до 236 ₽"),
        ("Как там моя цель?", "Ноутбук"),
    ],
)
async def test_fake_llm_round_trip(p1, question, fragment):
    llm = FakeLLM()
    messages = [{"role": "system", "content": "Сегодня: 2026-09-26."}, {"role": "user", "content": question}]
    first = await llm.complete(messages, tools=openai_tools())
    call: ToolCall = first.tool_calls[0]
    result = dispatch(call.name, call.arguments, p1)
    assert "error" not in result
    second = await llm.complete([*messages, tool_message(call, result)])
    assert fragment in json.loads(second.content)["result"]


def test_build_answer_handles_error():
    blocks = build_answer("simulate", {"error": "delay_days должно быть от 0 до 60"})
    assert "Не получилось посчитать" in blocks["result"]
