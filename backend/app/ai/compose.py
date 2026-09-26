"""Помощник формулирует текст вокруг чисел, которые уже посчитал core.

Модель сюда не подставляется: без неё сценарий хакатона остаётся воспроизводимым.
Если позже появится LLM, она должна получать этот же пакет чисел и не пересчитывать его.
"""

import re
from datetime import date
from decimal import Decimal

from app.ai.glossary import lookup
from app.ai.guard import EDUCATION_SOURCE, refusal
from app.core.analysis import build_forecast, build_goal_plan, build_overview, coverage_days
from app.core.calendar import build_impulse, build_runway, human_date
from app.core.explain import COMMON_LIMITS, explained, step
from app.money import D, fmt_rub

_AMOUNT = re.compile(
    r"(\d[\d \u00a0]{0,12}?)(?:[.,](\d{1,2}))?\s*(?:₽|руб(?:л(?:ей|я|ь|ями)?)?)",
    re.IGNORECASE,
)


def extract_amount(question: str) -> Decimal | None:
    currency = list(_AMOUNT.finditer(question))
    if currency:
        return _parse_amount(currency[-1].group(1), currency[-1].group(2))
    candidates: list[Decimal] = []
    for match in re.finditer(r"\d[\d \u00a0]{0,12}", question):
        digits = match.group(0).replace(" ", "").replace("\u00a0", "")
        if len(digits) == 4 and digits.startswith(("19", "20")):
            continue
        value = Decimal(digits)
        if value >= 50:
            candidates.append(value)
    return candidates[-1] if candidates else None


def _parse_amount(whole: str, fraction: str | None) -> Decimal:
    digits = whole.replace(" ", "").replace("\u00a0", "")
    text = digits if not fraction else f"{digits}.{fraction}"
    return D(text)


def answer(question: str, scenario_id: str, state: dict, as_of: date) -> dict:
    topic = refusal(question)
    if topic:
        return _refused(topic, as_of, state)

    if scenario_id == "glossary" or (scenario_id == "free" and _looks_like_glossary(question)):
        return _glossary(question, state, as_of)
    if scenario_id == "impulse" or (scenario_id == "free" and _looks_like_impulse(question)):
        return _impulse(question, state, as_of)
    if scenario_id == "expenses" or (scenario_id == "free" and _looks_like_expenses(question)):
        return _expenses(state, as_of)
    if scenario_id == "budget" or (scenario_id == "free" and _looks_like_budget(question)):
        return _budget(state, as_of)
    if scenario_id == "free":
        return _clarify(state, as_of)
    return _clarify(state, as_of)


def _looks_like_glossary(question: str) -> bool:
    folded = question.casefold()
    return folded.startswith("что такое") or "объясни" in folded


def _looks_like_impulse(question: str) -> bool:
    folded = question.casefold()
    return extract_amount(question) is not None and any(
        word in folded for word in ("куп", "покуп", "хватит", "потрат", "взять")
    )


def _looks_like_expenses(question: str) -> bool:
    folded = question.casefold()
    return any(word in folded for word in ("расход", "трат", "куда уход", "категор"))


def _looks_like_budget(question: str) -> bool:
    folded = question.casefold()
    return any(word in folded for word in ("бюджет", "накоп", "стипенд", "до зарплат", "хватит ли"))


def _coverage(state: dict, as_of: date) -> int:
    return coverage_days(state["transactions"], as_of)


def _refused(topic: str, as_of: date, state: dict) -> dict:
    text = (
        f"Я не разбираю вопросы про {topic} и не говорю, куда деть деньги. "
        "Могу показать, куда уходят расходы, хватит ли баланса до следующего поступления "
        "и как цель накопления стыкуется с вашими тратами."
    )
    return explained(
        {"text": text},
        assumptions=[],
        calculation=[],
        sources=[EDUCATION_SOURCE],
        limitations=[
            "Продукт не даёт инвестиционных рекомендаций и не принимает решение за вас.",
            "Секретные данные — пароли, коды, полные номера карт — сюда присылать не нужно.",
        ],
        sufficient=True,
        missing=[],
        coverage_days=_coverage(state, as_of),
    )


def _glossary(question: str, state: dict, as_of: date) -> dict:
    found = lookup(question)
    if found is None:
        return explained(
            {"text": ""},
            assumptions=[],
            calculation=[],
            sources=[],
            limitations=[
                "Отвечаю только по терминам с проверенным источником и не придумываю определения.",
            ],
            sufficient=False,
            missing=[
                "уточните термин: инфляция, вклад, кредитная история, подушка или подписка",
            ],
            coverage_days=_coverage(state, as_of),
        )
    text = f"{found['text']} Типичная ошибка: {found['mistake']}"
    return explained(
        {"text": text},
        assumptions=["Определение взято из проверенного источника, а не из свободной генерации."],
        calculation=[],
        sources=[{"title": found["title"], "url": found["url"]}],
        limitations=[
            "Это объяснение термина, а не рекомендация открывать вклад, брать кредит или инвестировать."
        ],
        sufficient=True,
        missing=[],
        coverage_days=_coverage(state, as_of),
    )


def _missing_dataset(state: dict) -> list[str]:
    missing = []
    if state["balance"] is None:
        missing.append("текущий баланс")
    if not state["transactions"]:
        missing.append("операции хотя бы за один месяц")
    return missing


def _expenses(state: dict, as_of: date) -> dict:
    missing = _missing_dataset(state)
    if "операции хотя бы за один месяц" in missing:
        return explained(
            {"text": ""},
            assumptions=[],
            calculation=[],
            sources=[],
            limitations=COMMON_LIMITS,
            sufficient=False,
            missing=missing or ["операции хотя бы за один месяц"],
            coverage_days=0,
        )
    overview = build_overview(state["transactions"], as_of)
    if not overview["_has_rows"]:
        return explained(
            {"text": ""},
            assumptions=[],
            calculation=[],
            sources=[],
            limitations=COMMON_LIMITS,
            sufficient=False,
            missing=["операции за текущий месяц"],
            coverage_days=_coverage(state, as_of),
        )
    lines = [
        f"{item['category']}: {fmt_rub(D(item['amount']))} ({round(item['share'] * 100)}%)"
        for item in overview["byCategory"][:3]
    ]
    anomaly = ""
    if overview["anomalies"]:
        anomaly = " " + overview["anomalies"][0]["reason"] + "."
    text = (
        f"С {human_date(date.fromisoformat(overview['periodFrom']))} расходы "
        f"{fmt_rub(overview['_total_expense'])}, из них регулярные {fmt_rub(overview['_recurring'])}. "
        f"Крупнее всего: {'; '.join(lines) or 'пока нет категорий'}.{anomaly} "
        "Сокращать логичнее разовые и необязательные статьи, а не аренду и проезд."
    )
    recurring_share = (
        0
        if overview["_total_expense"] == 0
        else int(overview["_recurring"] / overview["_total_expense"] * 100)
    )
    return explained(
        {"text": text},
        assumptions=[
            f"Период: {overview['periodFrom']} — {overview['periodTo']}.",
            "Регулярные — аренда, подписки, проезд и то, что повторяется из месяца в месяц.",
        ],
        calculation=[
            step("Расходы за период", "сумма операций со знаком минус", overview["_total_expense"]),
            step("из них регулярные", "операции с признаком «регулярный»", overview["_recurring"]),
            step(
                "Доля регулярных, %",
                f"{fmt_rub(overview['_recurring'])} / {fmt_rub(overview['_total_expense'])}",
                recurring_share,
            ),
        ],
        sources=[],
        limitations=COMMON_LIMITS,
        sufficient=True,
        missing=[],
        coverage_days=_coverage(state, as_of),
    )


def _budget(state: dict, as_of: date) -> dict:
    missing = []
    if state["balance"] is None:
        missing.append("текущий баланс")
    if not state["incomes"]:
        missing.append("хотя бы одно регулярное поступление: стипендия, зарплата или подработка")
    if missing:
        return explained(
            {"text": ""},
            assumptions=[],
            calculation=[],
            sources=[],
            limitations=COMMON_LIMITS,
            sufficient=False,
            missing=missing,
            coverage_days=_coverage(state, as_of),
        )
    forecast = build_forecast(state["balance"], state["incomes"], state["transactions"], as_of)
    runway = build_runway(state["balance"], state["incomes"], state["transactions"], as_of)
    goal = next((item for item in state["goals"] if item.get("deadline")), None)
    goal_sentence = ""
    calculation = [
        step("Текущий баланс", "остаток, который вы указали", forecast["_balance"]),
        step(
            "Обязательные до конца месяца",
            ", ".join(forecast["_planned_titles"]) or "нет платежей в загруженных данных",
            forecast["plannedExpenses"],
        ),
        step(
            "Остаток к концу месяца", "баланс + ожидаемые поступления − обязательные", forecast["_projected"]
        ),
        step(
            "Можно тратить в день до конца месяца",
            f"{fmt_rub(forecast['_projected'])} / {forecast['daysLeft']} дн.",
            forecast["_safe"],
        ),
    ]
    if goal:
        plan = build_goal_plan(goal, state["transactions"], as_of)
        if not plan["_missing"] and plan.get("_pace") is not None and not plan.get("_done"):
            pace_text = fmt_rub(plan["_pace"])
            goal_sentence = f" Чтобы успеть «{goal['title']}» к сроку,"
            goal_sentence += f" откладывайте около {pace_text} в месяц."
            calculation.append(step("На цель в месяц", "остаток цели / месяцы до срока", plan["_pace"]))
    nxt = runway["nextIncome"]
    until = ""
    if nxt:
        until = (
            f" До «{nxt['title']}» {nxt['daysUntil']} дн.,"
            f" безопасный расход {fmt_rub(D(runway['todaySafeSpend']))} в день."
        )
    text = (
        f"До конца месяца можно тратить около {fmt_rub(forecast['_safe'])} в день. "
        f"К последнему числу останется примерно {fmt_rub(forecast['_projected'])}.{until}{goal_sentence}"
    )
    assumptions = [
        "Поступления и обязательные платежи повторяются в те же дни месяца, что уже есть в данных."
    ]
    if not forecast["_planned_titles"]:
        assumptions.append(
            "До конца месяца в регулярных операциях нет новых списаний — ничего не додумано сверх данных."
        )
    if forecast["_expected_titles"]:
        assumptions.append("В этом месяце ещё ожидается: " + ", ".join(forecast["_expected_titles"]) + ".")
    else:
        assumptions.append("Новых поступлений до конца месяца в профиле нет.")
    return explained(
        {"text": text},
        assumptions=assumptions,
        calculation=calculation,
        sources=[],
        limitations=COMMON_LIMITS + ["Прогноз не учитывает покупку, которую вы ещё не внесли."],
        sufficient=True,
        missing=[],
        coverage_days=_coverage(state, as_of),
    )


def _impulse(question: str, state: dict, as_of: date) -> dict:
    amount = extract_amount(question)
    if amount is None or amount <= 0:
        return explained(
            {"text": ""},
            assumptions=[],
            calculation=[],
            sources=[],
            limitations=COMMON_LIMITS,
            sufficient=False,
            missing=["сумма покупки — сколько хотите потратить"],
            coverage_days=_coverage(state, as_of),
        )
    if state["balance"] is None:
        return explained(
            {"text": ""},
            assumptions=[],
            calculation=[],
            sources=[],
            limitations=COMMON_LIMITS,
            sufficient=False,
            missing=["текущий баланс"],
            coverage_days=_coverage(state, as_of),
        )
    check = build_impulse(
        state["balance"], state["incomes"], state["transactions"], state["goals"], as_of, amount
    )
    return explained(
        {"text": check["hint"]},
        assumptions=[
            "Покупка списывается сегодня, обязательные платежи остаются на своих датах.",
            "Поступления берутся из профиля и встают на тот же день месяца.",
        ],
        calculation=[
            step("Покупка", "сумма из вашего вопроса", amount),
            step(
                "Лимит в день до покупки",
                "свободные деньги / дни до поступления",
                D(check["todaySafeSpendBefore"]),
            ),
            step("Лимит в день после покупки", "то же после списания", D(check["todaySafeSpendAfter"])),
            step(
                "Минимальный остаток после покупки",
                "худший день на горизонте",
                D(check["lowestBalanceAfter"]),
            ),
        ],
        sources=[],
        limitations=COMMON_LIMITS,
        sufficient=True,
        missing=[],
        coverage_days=_coverage(state, as_of),
    )


def _clarify(state: dict, as_of: date) -> dict:
    return explained(
        {"text": ""},
        assumptions=[],
        calculation=[],
        sources=[],
        limitations=COMMON_LIMITS,
        sufficient=False,
        missing=[
            "уточните задачу: расходы, бюджет до поступления, термин или сумма покупки",
        ],
        coverage_days=_coverage(state, as_of),
    )
