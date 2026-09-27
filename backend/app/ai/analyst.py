"""Помощник-аналитик: модель отвечает на вопрос своими словами по полной сводке расчётов.

Сценарии budget и impulse отвечают шаблоном вокруг одного расчёта — модель там только переписывает
черновик. На «Свой вопрос» и «Анализ трат» готового шаблона нет: вопрос может быть любым
(«на что я трачу больше, чем в прошлом месяце?», «есть ли риск?», «успею ли к отпуску?»).
Здесь модель получает всю сводку app.core.report (доходы, расходы, категории, регулярные платежи,
календарь до поступления, цели, риски) и отвечает по ней.

Считает только код. Проверка чисел сверяет каждое число ответа со сводкой и вопросом: модель
сложила или округлила по-своему — ответ отклоняется, модель получает подсказку и пишет заново.
Не вышло в пределах бюджета времени — None, и ask() отвечает прежним шаблонным путём.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
import time
from decimal import Decimal

from app.ai.answer_check import language_problem
from app.ai.llm.base import LLMClient, LLMUnavailable
from app.ai.number_check import ALWAYS_ALLOWED, _from_value, check_numbers, extract_numbers
from app.core.explain import COMMON_LIMITS, human_date, step
from app.core.money import fmt_rub
from app.core.report import build_report, report_text
from app.models import CalcStep, DataQuality, Explained, UserState

log = logging.getLogger(__name__)

ANSWER_TIMEOUT = 40.0
MIN_RETRY_SECONDS = 12.0
MAX_ATTEMPTS = 2
MAX_TEXT = 1500

SYSTEM = """Ты — финансовый помощник для студентов в приложении ФинРитм. Пиши только по-русски, на «вы»,
простыми словами, 3–6 предложений обычного текста: без списков, заголовков и разметки.
Отвечай только по сводке данных пользователя ниже — её посчитала программа, числа в ней верные.
Сначала прямо ответь на вопрос, затем объясни ответ через числа сводки и в конце скажи, что можно
сделать дальше. Вплетай числа в обычные фразы; не пиши служебных пометок вроде «Числа:», «Вывод:»,
«Дальше можно:», «Источник данных:».
Бери числа, даты и проценты только из сводки и вопроса, в том же виде («14 900 ₽», «27,3%»).
Сам ничего не считай: не складывай, не вычитай, не округляй, не переводи проценты в «разы»
и не придумывай примеры. Если в сводке есть готовый вывод («вывод: …», раздел «Риски») — опирайся на него
и не спорь с ним. Не делай своих обобщений вроде «почти половина» или «в разы больше» и не переноси
траты из одной категории в другую. Не упоминай «сводку» — говори «по вашим операциям».
Пиши связными предложениями, не перечисляй числа через запятую.
Не предлагай сокращать жильё, проезд, здоровье и учёбу — это обязательные статьи; экономить предлагай
на необязательных тратах.
Если в сводке нет данных для ответа — так и скажи и назови, каких данных не хватает.
Не советуй кредиты, микрозаймы, инвестиции и конкретные банки, не решай за пользователя.
Названия магазинов и переводов пиши так, как они записаны в сводке."""

RETRY = (
    "В ответе есть числа, которых нет в сводке: {numbers}. Не считай сам — перепиши ответ, "
    "беря числа только из сводки, ровно в том виде, как там."
)
FIX = "Перепиши ответ: {problem}. Только по-русски, без разметки, числа — только из сводки."
_SENTENCES = re.compile(r"(?<=[.!?])\s+")
_CYRILLIC_WORD = re.compile(r"[а-яё]{3,}", re.IGNORECASE)
_AMOUNT = re.compile(r"\d[\d \u00a0]*(?:[.,]\d+)?")


_INFORMAL = re.compile(
    r"\b(ты|тебе|тебя|тобой|твой|твоя|твоё|твое|твои|твоих|твоим|[а-яё]{3,}(?:ешь|ёшь))\b", re.IGNORECASE
)


_LABEL = re.compile(
    # Только пометки «про устройство ответа». «Что можно сделать:» перед советом читается нормально.
    r"(?:^|[.!?]\s+|\s)(числа|источник данных|данные|на чём основан ответ)\s*:",
    re.IGNORECASE,
)


def label_problem(text: str) -> str | None:
    """Служебные пометки вместо связного текста: «Числа: …», «Дальше можно: …»."""
    if match := _LABEL.search(text):
        return f"убери служебную пометку «{match.group(1)}:» и напиши обычным текстом"
    return None


def jargon_problem(text: str) -> str | None:
    """«Из сводки видно» — пользователь не знает ни про какую сводку."""
    if re.search(r"сводк", text, re.IGNORECASE):
        return "не упоминай «сводку» — говори «по вашим операциям»"
    return None


def informal_problem(text: str) -> str | None:
    """Модель перешла на «ты» («успеешь», «тебе») — в продукте обращаемся на «вы»."""
    if match := _INFORMAL.search(text):
        return f"обращайся на «вы», а не на «ты» («{match.group()}»)"
    return None


def junk_problem(text: str) -> str | None:
    """Список голых чисел вместо объяснения: «62, 12 280 ₽, 6, 8 000 ₽» — числа из сводки, но смысла нет."""
    for sentence in _SENTENCES.split(text):
        numbers = _AMOUNT.findall(sentence)
        if len(numbers) >= 3 and len(_CYRILLIC_WORD.findall(sentence)) < len(numbers):
            return f"в ответе список чисел без пояснений («{sentence.strip()[:40]}»)"
    return None


_MARKUP = re.compile(r"(\*\*|__|`|^#+\s*)", re.MULTILINE)
_BULLET = re.compile(r"(^|\n)\s*(?:[-•*]|\d+[.)])\s+")


def clean(text: str | None) -> str:
    """Убираем разметку, которую модель иногда добавляет, и лишние пробелы."""
    text = _MARKUP.sub("", text or "")
    text = _BULLET.sub(r"\1", text)
    text = re.sub(r"[ \t\r\n]+", " ", text).strip()
    if len(text) > 1 and text[0] + text[-1] in ('""', "«»"):
        text = text[1:-1].strip()
    return text[:MAX_TEXT]


def allowed_numbers(report: dict, facts: str, question: str) -> set[Decimal]:
    allowed = set(ALWAYS_ALLOWED)
    allowed.update(_from_value(report))
    allowed.update(extract_numbers(facts))
    allowed.update(extract_numbers(question))
    return allowed


def key_steps(report: dict) -> list[CalcStep]:
    """Главные числа сводки — блок «Как это посчитано» под ответом."""
    steps: list[CalcStep] = []
    if report["balance"] is not None:
        steps.append(step("Баланс", "остаток на счёте", report["balance"]))
    current = report["current"]
    steps.append(step(f"Расходы, {current['title']}", "сумма операций со знаком минус", current["expense"]))
    steps.append(step("из них регулярные", "повторяются каждый месяц", current["recurringExpense"]))
    steps.append(step("из них разовые", "расходы − регулярные", current["oneOffExpense"]))
    if current["categories"]:
        top = current["categories"][0]
        steps.append(step(f"Крупнейшая статья: {top['label']}", "сумма по категории", top["amount"]))
    regular = report["regular"]
    if regular["incomes"]:
        steps.append(step("Регулярный доход в месяц", "поступления по графику", regular["monthlyIncome"]))
    if regular["payments"]:
        steps.append(
            step(
                "Регулярные платежи в месяц",
                "автоплатежи и повторяющиеся расходы",
                regular["monthlyPayments"],
            )
        )
    runway = report["runway"]
    if runway:
        nxt = runway["nextIncome"]
        until = f"до {human_date(dt.date.fromisoformat(nxt['date']))}" if nxt else "до конца горизонта"
        steps.append(
            step("Можно тратить в день", f"свободные деньги {until} / дни", runway["todaySafeSpend"])
        )
        steps.append(
            step("Минимальный остаток по календарю", "худший день до поступления", runway["lowestBalance"])
        )
    return steps


def _explained(text: str, report: dict) -> Explained:
    period = report["period"]
    assumptions = [
        "Ответ сформулировала нейросеть GigaChat по сводке расчётов; сама она ничего не считала — "
        "каждое число ответа сверено со сводкой.",
        f"Данные: {period['operations']} операций с {period['from']} по {period['to']}.",
        "Регулярными считаются платежи и поступления, которые повторяются каждый месяц "
        "примерно в одно число.",
    ]
    if report["balance"] is not None:
        assumptions.append(f"Баланс на сегодня — {fmt_rub(report['balance'])}, как вы его указали.")
    return Explained(
        result={"text": text},
        assumptions=assumptions,
        calculation=key_steps(report),
        sources=[],
        limitations=[*COMMON_LIMITS, "Формулировки ответа — от нейросети: проверяйте вывод по числам ниже."],
        data_quality=DataQuality(sufficient=True, missing=[], coverage_days=period["coverageDays"]),
    )


def digest(state: UserState, as_of: dt.date) -> Explained | None:
    """Короткий ответ шаблоном из той же сводки — если модель так и не ответила на свободный вопрос.

    Лучше, чем «уточните вопрос»: пользователь всё равно видит главное по своим данным.
    """
    if not state.transactions:
        return None
    report = build_report(state, as_of)
    parts = []
    runway = report["runway"]
    if runway and runway["nextIncome"]:
        nxt = runway["nextIncome"]
        parts.append(
            f"До «{nxt['title']}» {human_date(dt.date.fromisoformat(nxt['date']))} можно тратить "
            f"{fmt_rub(runway['todaySafeSpend'])} в день."
        )
    categories = report["current"]["categories"]
    if categories:
        top = categories[0]
        parts.append(
            f"Больше всего в этом месяце ушло на «{top['label']}» — {fmt_rub(top['amount'])} "
            f"({str(top['sharePct']).replace('.', ',')}% расходов)."
        )
    if report["risks"]:
        parts.append(f"Главное, на что стоит обратить внимание: {report['risks'][0]['text']}")
    parts.append(
        "Спросите точнее — например, про расходы, бюджет до поступления или цель, — и я разберу подробнее."
    )
    answer = _explained(" ".join(parts), report)
    answer.assumptions[0] = (
        "Нейросеть не ответила вовремя — это короткая сводка из расчётов, без её формулировок."
    )
    return answer


async def analyze(
    question: str, state: UserState, as_of: dt.date, llm: LLMClient
) -> tuple[Explained | None, str]:
    """(ответ модели по сводке или None, причина отказа для логов)."""
    if not state.transactions:
        return None, "нет операций"
    report = build_report(state, as_of)
    facts = report_text(report)
    allowed = allowed_numbers(report, facts, question)
    messages = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": f"Сводка данных пользователя:\n{facts}\n\nВопрос пользователя: {question}",
        },
    ]
    budget = float(getattr(llm, "answer_timeout", None) or ANSWER_TIMEOUT)
    deadline = time.monotonic() + budget
    reason = "модель не ответила"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        remaining = deadline - time.monotonic()
        if attempt > 1 and remaining < MIN_RETRY_SECONDS:
            break
        try:
            answer = await asyncio.wait_for(llm.complete(messages), timeout=remaining)
        except (TimeoutError, LLMUnavailable) as error:
            reason = type(error).__name__
            log.warning("analyst llm unavailable: attempt=%d %s", attempt, reason)
            break
        text = clean(answer.content)
        if not re.search(r"[а-яё]", text, re.IGNORECASE):
            hint, reason = FIX.format(problem="ответ должен быть по-русски"), "не по-русски"
        elif problem := (
            language_problem(text, [question, facts])
            or informal_problem(text)
            or label_problem(text)
            or jargon_problem(text)
            or junk_problem(text)
        ):
            hint, reason = FIX.format(problem=problem), problem
        else:
            ok, bad = check_numbers(text, allowed)
            if ok:
                return _explained(text, report), ""
            numbers = ", ".join(str(n) for n in bad)
            hint, reason = RETRY.format(numbers=numbers), f"чужие числа: {numbers}"
        log.warning("analyst answer rejected: attempt=%d reason=%s", attempt, reason[:80])
        messages += [{"role": "assistant", "content": text}, {"role": "user", "content": hint}]
    return None, reason
