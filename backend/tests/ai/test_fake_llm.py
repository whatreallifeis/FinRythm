import datetime as dt
import json
import re
from decimal import Decimal

import pytest
from app.ai.llm.base import LLMReply, ToolCall, assistant_message, tool_message
from app.ai.llm.fake import FakeLLM, extract_amount
from app.models import (
    Assumption,
    Breakdown,
    CategoryStat,
    GoalPlan,
    Risk,
    RiskReport,
    RunwayResult,
    SimulationResult,
)

SYSTEM = {"role": "system", "content": "Ты финансовый помощник. Сегодня: 2026-09-26."}


def user(text: str) -> dict:
    return {"role": "user", "content": text}


async def first_call(question: str) -> ToolCall:
    reply = await FakeLLM().complete([SYSTEM, user(question)], tools=[])
    assert reply.content is None
    assert len(reply.tool_calls) == 1
    return reply.tool_calls[0]


# ---------------------------------------------------------------- 1-й вызов: выбор инструмента

QUESTIONS = [
    ("Хватит ли на концерт за 3000, если я коплю на ноутбук?", "simulate", {"purchase": 3000}),
    ("Хочу купить кроссовки за 3 000", "simulate", {"purchase": 3000}),
    ("Можно потратить 3к на подарок?", "simulate", {"purchase": 3000}),
    ("Думаю про покупку наушников за 2,5 тыс", "simulate", {"purchase": 2500}),
    ("Что будет, если стипендию задержат на неделю?", "simulate", {"delay_days": 7}),
    ("А если деньги за подработку придут позже на 10 дней?", "simulate", {"delay_days": 10}),
    ("Стипендию задерживают на 2 недели, что делать?", "simulate", {"delay_days": 14}),
    (
        "Хочу накопить на ноутбук 60 000 к 31 марта",
        "plan_goal",
        {"target_amount": 60000, "deadline": "2027-03-31"},
    ),
    ("Как мне копить на поездку?", "plan_goal", {}),
    ("Куда уходят мои деньги?", "spending_breakdown", {}),
    ("Покажи расходы по категориям", "spending_breakdown", {}),
    ("Есть ли у меня риски?", "detect_risks", {}),
    ("Когда закончатся деньги?", "detect_risks", {}),
    ("Что такое финансовая подушка?", "search_knowledge", {"query": "Что такое финансовая подушка?"}),
    ("Объясни, что такое подписка", "search_knowledge", {"query": "Объясни, что такое подписка"}),
    ("Сколько я могу тратить в день?", "calculate_runway", {}),
    ("Хватит ли на еду до стипендии?", "calculate_runway", {}),
]


@pytest.mark.parametrize(("question", "tool", "args"), QUESTIONS)
async def test_first_call_picks_tool(question, tool, args):
    call = await first_call(question)
    assert call.name == tool
    assert call.arguments == args


async def test_first_call_is_case_insensitive():
    call = await first_call("КУДА УХОДЯТ МОИ ДЕНЬГИ?")
    assert call.name == "spending_breakdown"


async def test_delay_is_capped_by_schema_maximum():
    call = await first_call("Стипендию задержат на 90 дней")
    assert call.arguments == {"delay_days": 60}


async def test_goal_deadline_with_explicit_date():
    call = await first_call("Хочу отложить 15 000 до 01.06.2027")
    assert call.arguments == {"target_amount": 15000, "deadline": "2027-06-01"}


async def test_goal_date_without_system_date_uses_today():
    reply = await FakeLLM().complete([user("Коплю 5000 к 1 января")])
    deadline = dt.date.fromisoformat(reply.tool_calls[0].arguments["deadline"])
    assert (deadline.month, deadline.day) == (1, 1)
    assert deadline >= dt.date.today()


async def test_first_tool_call_id():
    llm = FakeLLM()
    first = await llm.complete([SYSTEM, user("Есть ли у меня риски?")])
    assert first.tool_calls[0].id == "call_1"


@pytest.mark.parametrize(
    ("text", "amount"),
    [
        ("за 3000", Decimal("3000")),
        ("за 3 000 ₽", Decimal("3000")),
        ("за 3 000", Decimal("3000")),
        ("3к", Decimal("3000")),
        ("3 тыс", Decimal("3000")),
        ("3 тысячи", Decimal("3000")),
        ("1,5к", Decimal("1500")),
        ("499.90", Decimal("499.90")),
        ("без суммы", None),
    ],
)
def test_extract_amount(text, amount):
    assert extract_amount(text) == amount


# ---------------------------------------------------------------- 2-й вызов: ответ из результата


def runway(**kw) -> RunwayResult:
    base = dict(
        status="ok",
        as_of=dt.date(2026, 9, 26),
        next_income_date=dt.date(2026, 10, 10),
        next_income_title="Стипендия",
        horizon_days=14,
        balance=Decimal("9800.00"),
        mandatory_total=Decimal("1949.00"),
        free=Decimal("7851.00"),
        reserve=Decimal("785.10"),
        goal_contribution=Decimal("1400.00"),
        available=Decimal("5665.90"),
        daily_limit=Decimal("404"),
    )
    base.update(kw)
    return RunwayResult(**base)


async def second_call(tool: str, args: dict, result: dict, question: str = "вопрос") -> dict:
    call = ToolCall(id="call_1", name=tool, arguments=args)
    messages = [
        SYSTEM,
        user(question),
        assistant_message(LLMReply(content=None, tool_calls=[call])),
        tool_message(call, result),
    ]
    reply = await FakeLLM().complete(messages, tools=[])
    assert reply.tool_calls == []
    blocks = json.loads(reply.content)
    assert set(blocks) == {"result", "basis", "assumptions", "next_steps"}
    return blocks


def numbers_in(text: str) -> set[Decimal]:
    found = re.findall(r"\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?", text)
    return {Decimal(re.sub(r"[  ]", "", n).replace(",", ".")) for n in found}


def allowed_numbers(value) -> set[Decimal]:
    """Числа из результата инструмента + их округление до рубля + части дат."""
    out: set[Decimal] = set()
    if isinstance(value, dict):
        for v in value.values():
            out |= allowed_numbers(v)
    elif isinstance(value, list):
        for v in value:
            out |= allowed_numbers(v)
    elif isinstance(value, bool) or value is None:
        pass
    elif isinstance(value, int | float):
        out.add(Decimal(str(value)))
    elif isinstance(value, str):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            out |= {Decimal(p) for p in value.split("-")}
        for n in numbers_in(value):
            out |= {n, n.quantize(Decimal("1"))}
    return out


def assert_only_result_numbers(blocks: dict, result: dict) -> None:
    text = json.dumps(blocks, ensure_ascii=False)
    extra = numbers_in(text) - allowed_numbers(result)
    assert not extra, f"числа не из результата: {extra}\n{text}"


async def test_simulate_purchase_answer():
    result = SimulationResult(
        purchase=Decimal("3000"),
        before=runway(),
        after=runway(free=Decimal("4851.00"), reserve=Decimal("485.10"), daily_limit=Decimal("211")),
        delta_daily_limit=Decimal("-193"),
    ).model_dump(mode="json")
    blocks = await second_call("simulate", {"purchase": 3000}, result)
    assert "Если потратить 3 000 ₽, дневной лимит снизится с 404 ₽ до 211 ₽ на 14 дней" in blocks["result"]
    assert_only_result_numbers(blocks, result)


async def test_simulate_delay_answer():
    result = SimulationResult(
        delay_days=7,
        before=runway(),
        after=runway(horizon_days=21, daily_limit=Decimal("236")),
        delta_daily_limit=Decimal("-168"),
    ).model_dump(mode="json")
    blocks = await second_call("simulate", {"delay_days": 7}, result)
    assert "7 дней" in blocks["result"]
    assert "с 404 ₽ до 236 ₽" in blocks["result"]
    assert_only_result_numbers(blocks, result)


async def test_simulate_into_deficit_answer():
    result = SimulationResult(
        purchase=Decimal("9000"),
        before=runway(),
        after=runway(status="deficit", daily_limit=Decimal("0"), deficit=Decimal("1149.00")),
        delta_daily_limit=Decimal("-404"),
    ).model_dump(mode="json")
    blocks = await second_call("simulate", {"purchase": 9000}, result)
    assert "не хватит 1 149 ₽" in blocks["result"]
    assert_only_result_numbers(blocks, result)


async def test_runway_ok_answer():
    result = runway(
        formula_text="(9800 − 1949 − 785,10 − 1400) / 14 = 404",
        assumptions=[Assumption(code="expected_income_ignored", text="Подработка не учтена: это не факт")],
    ).model_dump(mode="json")
    blocks = await second_call("calculate_runway", {}, result)
    assert "404 ₽ в день" in blocks["result"]
    assert "10 октября" in blocks["result"]
    assert "(9800 − 1949 − 785,10 − 1400) / 14 = 404" in blocks["basis"]
    assert blocks["assumptions"] == ["Подработка не учтена: это не факт"]
    assert_only_result_numbers(blocks, result)


async def test_runway_deficit_answer():
    result = runway(status="deficit", daily_limit=Decimal("0"), deficit=Decimal("700.00")).model_dump(
        mode="json"
    )
    blocks = await second_call("calculate_runway", {}, result)
    assert "Дефицит 700 ₽ до 10 октября" in blocks["result"]
    assert_only_result_numbers(blocks, result)


async def test_runway_insufficient_data_answer():
    result = RunwayResult(
        status="insufficient_data",
        as_of=dt.date(2026, 9, 26),
        missing=[{"field": "balance", "message": "Укажите текущий баланс, без него лимит не посчитать"}],
    ).model_dump(mode="json")
    blocks = await second_call("calculate_runway", {}, result)
    assert "Укажите текущий баланс" in blocks["result"]


async def test_plan_goal_answer():
    result = GoalPlan(
        goal_id="g1",
        title="Ноутбук",
        target_amount=Decimal("60000"),
        saved_amount=Decimal("0"),
        deadline=dt.date(2027, 3, 31),
        days_left=186,
        required_daily=Decimal("323"),
        current_daily=Decimal("100"),
        amount_by_deadline=Decimal("18600.00"),
        projected_date=dt.date(2028, 5, 18),
        on_track=False,
    ).model_dump(mode="json")
    blocks = await second_call("plan_goal", {"goal_id": "g1"}, result)
    assert "323 ₽ в день" in blocks["result"]
    assert "31 марта 2027" in blocks["result"]
    assert "18 мая 2028" in blocks["basis"]
    assert_only_result_numbers(blocks, result)


async def test_breakdown_answer():
    result = Breakdown(
        period_from=dt.date(2026, 8, 27),
        period_to=dt.date(2026, 9, 26),
        total_expenses=Decimal("12500.00"),
        total_income=Decimal("15000.00"),
        categories=[
            CategoryStat(category="Еда", total=Decimal("7500.00"), share_pct=Decimal("60.0"), count=20),
            CategoryStat(category="Транспорт", total=Decimal("5000.00"), share_pct=Decimal("40.0"), count=8),
        ],
        recurring=[],
        large=[],
    ).model_dump(mode="json")
    blocks = await second_call("spending_breakdown", {}, result)
    assert "12 500 ₽" in blocks["result"]
    assert "Еда" in blocks["result"]
    assert "60,0 %" in blocks["result"]
    assert_only_result_numbers(blocks, result)


async def test_risks_answer():
    result = RiskReport(
        risks=[
            Risk(kind="subscription", severity="warning", title="Музыка", details="299 ₽ в месяц"),
            Risk(kind="subscription", severity="warning", title="Кино", details="299 ₽ в месяц"),
        ],
        balance_zero_date=dt.date(2026, 10, 20),
    ).model_dump(mode="json")
    blocks = await second_call("detect_risks", {}, result)
    assert "Музыка" in blocks["result"]
    assert "20 октября" in blocks["result"]
    assert_only_result_numbers(blocks, result)


async def test_risks_empty_answer():
    blocks = await second_call("detect_risks", {}, {"risks": [], "balance_zero_date": None})
    assert "не нашёл" in blocks["result"]


async def test_knowledge_answer_uses_first_fragment():
    result = {
        "results": [
            {
                "id": "kb-001",
                "title": "Финансовая подушка безопасности",
                "text": "Финансовая подушка — запас денег на непредвиденные случаи.",
                "source_title": "Банк России",
                "url": "https://fincult.info/x",
                "checked_at": "2026-09-26",
            }
        ]
    }
    blocks = await second_call("search_knowledge", {"query": "подушка"}, result)
    assert blocks["result"] == "Финансовая подушка — запас денег на непредвиденные случаи."
    assert "Банк России" in blocks["basis"]


async def test_knowledge_empty_answer():
    blocks = await second_call("search_knowledge", {"query": "блокчейн"}, {"results": []})
    assert "нет проверенного ответа" in blocks["result"]


async def test_tool_error_is_reported():
    blocks = await second_call("plan_goal", {}, {"error": "У тебя нет целей. Укажи сумму и срок."})
    assert "У тебя нет целей. Укажи сумму и срок." in blocks["result"]


async def test_answer_is_built_from_last_tool_result():
    first = ToolCall(id="call_1", name="detect_risks", arguments={})
    second = ToolCall(id="call_2", name="search_knowledge", arguments={"query": "подушка"})
    messages = [
        SYSTEM,
        user("вопрос"),
        assistant_message(LLMReply(content=None, tool_calls=[first])),
        tool_message(first, {"risks": [], "balance_zero_date": None}),
        assistant_message(LLMReply(content=None, tool_calls=[second])),
        tool_message(second, {"results": []}),
    ]
    reply = await FakeLLM().complete(messages)
    assert "нет проверенного ответа" in json.loads(reply.content)["result"]
