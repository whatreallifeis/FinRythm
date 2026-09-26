"""FakeLLM — детерминированная имитация модели без сети (спецификация §7.4).

1-й вызов (в истории нет результатов инструментов) — выбирает инструмент по ключевым словам вопроса.
2-й вызов (есть результат инструмента) — собирает ответ-JSON AnswerBlocks по шаблону
только из чисел последнего результата инструмента.

Дату «сегодня» (нужна, чтобы понять год в «к 31 марта») FakeLLM берёт из первой даты
ГГГГ-ММ-ДД в системном промпте, а если её нет — из системных часов.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.ai.llm.base import LLMReply, ToolCall

MONTHS = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]

MAX_DELAY_DAYS = 60  # maximum из contracts/tools.schema.json
DEFAULT_DELAY_DAYS = 7

_AMOUNT = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:[  ]\d{3})+|\d+)(?:[.,](\d+))?(?:([кk])(?![а-яa-z])|\s?(тыс)[а-я]*\.?)?"
)
_TEXT_DATE = re.compile(r"(?<!\d)(\d{1,2})\s+(" + "|".join(MONTHS) + r")(?:\s+(\d{4}))?")
_NUM_DATE = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?(?![\d.])")
_GOAL = re.compile(r"накоп|коплю|копить|отложить|\bцел(?:ь|и|ью|ей|ям|ями|ях)\b")

_KNOWLEDGE = ("что такое", "объясни", "как работает", "что значит")
_PURCHASE = ("купить", "купл", "потратить", "хватит ли на", "покупк")
_DELAY = ("задерж", "не придет", "не придут", "позже")
_BREAKDOWN = ("куда уходят", "траты", "расход", "категор")
_RISKS = ("риск", "подписк", "опасн", "закончатся")


# ---------------------------------------------------------------- разбор вопроса


def extract_amount(text: str) -> Decimal | None:
    """Первая сумма в тексте: «3000», «3 000», «3к», «3 тыс», «1,5к» → Decimal."""
    match = _AMOUNT.search(text.lower())
    if not match:
        return None
    whole, fraction, k_suffix, thousand = match.groups()
    value = Decimal(re.sub(r"[  ]", "", whole) + (f".{fraction}" if fraction else ""))
    if k_suffix or thousand:
        value *= 1000
    return value


def _rubles(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _delay_days(text: str) -> int:
    if match := re.search(r"(\d+)\s*(?:дн|ден)", text):
        days = int(match.group(1))
    elif match := re.search(r"(\d+)\s*недел", text):
        days = int(match.group(1)) * 7
    elif "две недели" in text:
        days = 14
    elif "три недели" in text:
        days = 21
    elif "месяц" in text:
        days = 30
    else:
        days = DEFAULT_DELAY_DAYS
    return min(days, MAX_DELAY_DAYS)


def _make_date(day: int, month: int, year: int | None, today: dt.date) -> dt.date | None:
    try:
        if year:
            return dt.date(year, month, day)
        candidate = dt.date(today.year, month, day)
        return candidate if candidate >= today else dt.date(today.year + 1, month, day)
    except ValueError:
        return None


def _extract_date(text: str, today: dt.date) -> tuple[dt.date | None, str]:
    """Дата из вопроса и текст без неё (чтобы день не приняли за сумму)."""
    if match := _TEXT_DATE.search(text):
        day, month = int(match.group(1)), MONTHS.index(match.group(2)) + 1
    elif match := _NUM_DATE.search(text):
        day, month = int(match.group(1)), int(match.group(2))
    else:
        return None, text
    year = int(match.group(3)) if match.group(3) else None
    rest = text[: match.start()] + " " + text[match.end() :]
    return _make_date(day, month, year, today), rest


def _goal_args(text: str, today: dt.date) -> dict:
    deadline, rest = _extract_date(text, today)
    amount = extract_amount(rest)
    if deadline and amount:
        return {"target_amount": _rubles(amount), "deadline": deadline.isoformat()}
    # Без суммы и срока tools.dispatch берёт первую цель пользователя.
    return {}


def choose_tool(question: str, today: dt.date) -> tuple[str, dict]:
    text = question.lower().replace("ё", "е")
    if any(k in text for k in _KNOWLEDGE):
        return "search_knowledge", {"query": question.strip()}
    if any(k in text for k in _PURCHASE) and (amount := extract_amount(text)) is not None:
        return "simulate", {"purchase": _rubles(amount)}
    if any(k in text for k in _DELAY):
        return "simulate", {"delay_days": _delay_days(text)}
    if _GOAL.search(text):
        return "plan_goal", _goal_args(text, today)
    if any(k in text for k in _BREAKDOWN):
        return "spending_breakdown", {}
    if any(k in text for k in _RISKS):
        return "detect_risks", {}
    return "calculate_runway", {}


# ---------------------------------------------------------------- форматирование


def _rub(value: Any) -> str:
    return f"{_rubles(Decimal(str(value))):,}".replace(",", " ") + " ₽"


def _pct(value: Any) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.1"))).replace(".", ",") + " %"


def _date(value: str, with_year: bool = False) -> str:
    d = dt.date.fromisoformat(value)
    return f"{d.day} {MONTHS[d.month - 1]}" + (f" {d.year}" if with_year else "")


def _days(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        word = "день"
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        word = "дня"
    else:
        word = "дней"
    return f"{n} {word}"


def _blocks(
    result: str, basis: str, assumptions: list[str] | None = None, next_steps: list[str] | None = None
):
    return {
        "result": result,
        "basis": basis,
        "assumptions": assumptions or [],
        "next_steps": next_steps or [],
    }


def _assumption_texts(runway: dict) -> list[str]:
    return [a["text"] for a in runway.get("assumptions", [])]


# ---------------------------------------------------------------- шаблоны ответов


def _answer_runway(r: dict) -> dict:
    if r["status"] == "insufficient_data":
        missing = " ".join(m["message"] for m in r.get("missing", [])) or "Не хватает данных для расчёта."
        return _blocks(missing, "Без этих данных лимит не посчитать.", [], ["Добавь недостающие данные."])
    if r.get("next_income_date"):
        till = f"до {_date(r['next_income_date'])}"
    else:
        till = f"на {_days(r['horizon_days'])}"
    basis = r.get("formula_text") or (
        f"Баланс {_rub(r['balance'])}, обязательные платежи {_rub(r['mandatory_total'])}, "
        f"резерв {_rub(r['reserve'])}, взнос в цели {_rub(r['goal_contribution'])}."
    )
    if r["status"] == "deficit":
        return _blocks(
            f"Дефицит {_rub(r['deficit'])} {till}. Безопасно тратить сейчас не получится.",
            basis,
            _assumption_texts(r),
            [
                "Посмотри, какие траты можно отложить до следующего поступления.",
                "Взнос в цель можно временно приостановить.",
            ],
        )
    return _blocks(
        f"Твой безопасный лимит — {_rub(r['daily_limit'])} в день {till}, это {_days(r['horizon_days'])}.",
        basis,
        _assumption_texts(r),
        ["Спроси «хватит ли на покупку за …», и я покажу, как изменится лимит."],
    )


def _answer_simulate(r: dict) -> dict:
    before, after = r["before"], r["after"]
    parts = []
    if Decimal(str(r.get("purchase", "0"))) > 0:
        parts.append(f"потратить {_rub(r['purchase'])}")
    if r.get("delay_days"):
        parts.append(f"поступление задержится на {_days(r['delay_days'])}")
    condition = "Если " + (" и ".join(parts) or "ничего не менять")

    if after["status"] == "insufficient_data":
        return _answer_runway(after)
    if after["status"] == "deficit":
        result = f"{condition}, до следующего поступления не хватит {_rub(after['deficit'])}."
    else:
        was, now = Decimal(str(before["daily_limit"])), Decimal(str(after["daily_limit"]))
        if now == was:
            result = (
                f"{condition}, дневной лимит не изменится: {_rub(now)} на {_days(after['horizon_days'])}."
            )
        else:
            verb = "снизится" if now < was else "вырастет"
            result = (
                f"{condition}, дневной лимит {verb} с {_rub(was)} до {_rub(now)} "
                f"на {_days(after['horizon_days'])}."
            )

    basis = f"Сейчас лимит {_rub(before['daily_limit'])} в день на {_days(before['horizon_days'])}."
    if Decimal(str(after.get("goal_contribution", "0"))) > 0:
        basis += f" Взнос в цели ({_rub(after['goal_contribution'])}) сохраняется."
    next_steps = []
    if parts and Decimal(str(r.get("purchase", "0"))) > 0:
        next_steps.append(
            "Если покупка не срочная, её можно перенести на время после следующего поступления."
        )
    if r.get("delay_days"):
        next_steps.append("Заранее реши, какие траты можно сократить на время задержки.")
    return _blocks(result, basis, _assumption_texts(after), next_steps)


def _answer_plan_goal(r: dict) -> dict:
    result = (
        f"Чтобы собрать {_rub(r['target_amount'])} на «{r['title']}» к {_date(r['deadline'], True)}, "
        f"нужно откладывать {_rub(r['required_daily'])} в день."
    )
    basis = f"До срока {_days(r['days_left'])}."
    if Decimal(str(r["saved_amount"])) > 0:
        basis += f" Уже накоплено {_rub(r['saved_amount'])}."
    if Decimal(str(r["current_daily"])) > 0:
        basis += (
            f" Сейчас ты откладываешь {_rub(r['current_daily'])} в день: "
            f"к сроку будет {_rub(r['amount_by_deadline'])}"
        )
        if r.get("projected_date"):
            basis += f", а вся сумма наберётся к {_date(r['projected_date'], True)}"
        basis += "."
    else:
        basis += " Сейчас на эту цель ничего не откладывается."
    if r["on_track"]:
        next_steps = ["Текущего темпа хватает, чтобы успеть к сроку."]
    else:
        next_steps = ["Можно увеличить ежедневный взнос, сдвинуть срок или уменьшить сумму цели."]
    return _blocks(result, basis, ["Считаю, что каждый день откладывается одинаковая сумма."], next_steps)


def _answer_breakdown(r: dict) -> dict:
    period = f"с {_date(r['period_from'])} по {_date(r['period_to'])}"
    categories = sorted(r["categories"], key=lambda c: Decimal(str(c["total"])), reverse=True)[:3]
    if not categories:
        return _blocks(f"За период {period} расходов не найдено.", "Смотрел операции за этот период.")
    top = ", ".join(f"{c['category']} — {_pct(c['share_pct'])} ({_rub(c['total'])})" for c in categories)
    result = f"За период {period} расходы — {_rub(r['total_expenses'])}. Больше всего уходит на: {top}."
    basis = f"Операции за период {period}. Доходы за это время — {_rub(r['total_income'])}."
    if r.get("recurring"):
        items = ", ".join(f"{i['description']} — {_rub(i['monthly_cost'])} в месяц" for i in r["recurring"])
        basis += f" Регулярные платежи: {items}."
    if r.get("large"):
        items = ", ".join(f"{t['description']} — {_rub(abs(Decimal(t['amount'])))}" for t in r["large"])
        basis += f" Крупные траты: {items}."
    return _blocks(result, basis, [], ["Присмотрись к самой крупной категории: там проще всего сэкономить."])


def _answer_risks(r: dict) -> dict:
    basis = "Проверил подписки, крупные траты и остаток до следующего поступления."
    if not r["risks"]:
        return _blocks("Серьёзных рисков я не нашёл.", basis)
    result = "Вот что стоит учесть: " + "; ".join(f"{x['title']} — {x['details']}" for x in r["risks"]) + "."
    if r.get("balance_zero_date"):
        result += f" При текущем темпе трат деньги закончатся около {_date(r['balance_zero_date'])}."
    next_steps = []
    if any(x["kind"] == "subscription" for x in r["risks"]):
        next_steps.append("Проверь, всеми ли подписками ты пользуешься.")
    return _blocks(result, basis, [], next_steps)


def _answer_knowledge(r: dict | list) -> dict:
    fragments = r.get("results", []) if isinstance(r, dict) else r
    if not fragments:
        return _blocks(
            "В моей базе нет проверенного ответа на этот вопрос.",
            "Я объясняю термины только по проверенной базе знаний.",
        )
    first = fragments[0]
    return _blocks(first["text"], f"Источник: {first.get('source_title') or first['title']}.")


_ANSWERS = {
    "calculate_runway": _answer_runway,
    "simulate": _answer_simulate,
    "plan_goal": _answer_plan_goal,
    "spending_breakdown": _answer_breakdown,
    "detect_risks": _answer_risks,
    "search_knowledge": _answer_knowledge,
}


def build_answer(tool: str, result: Any) -> dict:
    if isinstance(result, dict) and "error" in result:
        return _blocks(f"Не получилось посчитать: {result['error']}", "Инструмент вернул ошибку.", [], [])
    if tool in _ANSWERS:
        return _ANSWERS[tool](result)
    if isinstance(result, dict) and result.get("balance") is not None:
        return _blocks(f"Сейчас на балансе {_rub(result['balance'])}.", "Сводка твоих данных.")
    return _blocks("Данные получены.", "Сводка твоих данных.")


# ---------------------------------------------------------------- клиент


def _today(messages: list[dict]) -> dt.date:
    for message in messages:
        if message.get("role") == "system":
            if match := re.search(r"\d{4}-\d{2}-\d{2}", message.get("content") or ""):
                return dt.date.fromisoformat(match.group())
    return dt.date.today()


def _tool_name(messages: list[dict], tool_msg: dict) -> str:
    if tool_msg.get("name"):
        return tool_msg["name"]
    for message in messages:
        for call in message.get("tool_calls") or []:
            if call["id"] == tool_msg.get("tool_call_id"):
                return call["function"]["name"]
    return ""


class FakeLLM:
    name = "fake"

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMReply:
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        if tool_msgs:
            last = tool_msgs[-1]
            blocks = build_answer(_tool_name(messages, last), json.loads(last["content"]))
            return LLMReply(content=json.dumps(blocks, ensure_ascii=False), tool_calls=[])

        question = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        name, arguments = choose_tool(question, _today(messages))
        return LLMReply(content=None, tool_calls=[ToolCall(id="call_1", name=name, arguments=arguments)])
