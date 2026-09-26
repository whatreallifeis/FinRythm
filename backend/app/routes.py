"""HTTP-слой. Считает не он: числа приходят из core и ai.compose."""

import re
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ai.compose import answer
from app.clock import today
from app.core.analysis import build_forecast, build_goal_plan, build_overview, coverage_days
from app.core.calendar import build_impulse, build_runway
from app.core.explain import COMMON_LIMITS, explained, step
from app.identity import TelegramAuthError, user_id_for_telegram, verify_init_data
from app.money import D, fmt_rub
from app.storage import Store, balance_of, public_profile, public_transactions

CATEGORIES = {"food", "transport", "subscriptions", "entertainment", "health", "education", "rent", "other"}
CARD_RE = re.compile(r"(?:\d[ -]?){13,19}")
RECURRING_WORDS = ("подписк", "аренд", "проезд", "связь", "интернет", "кинотеатр", "музык", "мобильн")

router = APIRouter(prefix="/api")


def get_store() -> Store:
    raise RuntimeError("Зависимость Store не подключена")


class IncomeIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | None = None
    title: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    dayOfMonth: int = Field(ge=1, le=31)


class ProfileIn(BaseModel):
    balance: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    incomes: list[IncomeIn]


class GoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    targetAmount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    savedAmount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    deadline: date | None = None

    @model_validator(mode="after")
    def saved_not_above_target(self):
        if self.savedAmount > self.targetAmount:
            raise ValueError("накоплено не может быть больше суммы цели")
        return self


class ImpulseIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    scenarioId: str

    @field_validator("scenarioId")
    @classmethod
    def known_scenario(cls, value: str) -> str:
        allowed = {"expenses", "budget", "glossary", "impulse", "free"}
        if value not in allowed:
            raise ValueError("неизвестный сценарий")
        return value


class TelegramIn(BaseModel):
    initData: str = Field(min_length=1)


class ImportRowIn(BaseModel):
    date: date
    amount: Decimal
    category: str = "other"
    merchant: str = ""


class ImportIn(BaseModel):
    rows: list[ImportRowIn]


def current_session(
    authorization: str | None = Header(default=None),
    store: Store = Depends(get_store),
) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Нужно войти, чтобы видеть свои данные.")
    token = authorization.split(" ", 1)[1].strip()
    session = store.session(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Сессия недействительна. Войдите снова.")
    return session


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


@router.post("/auth/demo")
def auth_demo(store: Store = Depends(get_store)) -> dict:
    token = uuid.uuid4().hex
    user_id = f"web:{uuid.uuid4().hex[:16]}"
    store.create_session(token, user_id, "Демо-режим", "demo")
    return {"token": token, "userId": user_id, "displayName": "Демо-режим", "mode": "demo"}


@router.post("/auth/telegram")
def auth_telegram(body: TelegramIn, store: Store = Depends(get_store)) -> dict:
    from app.config import get_settings

    settings = get_settings()
    try:
        profile = verify_init_data(body.initData, settings.telegram_bot_token)
    except TelegramAuthError as error:
        status = 503 if "не настроен" in error.message else 401
        raise HTTPException(status_code=status, detail=error.message) from error
    user_id = user_id_for_telegram(profile["id"], settings.tg_id_salt)
    token = uuid.uuid4().hex
    store.create_session(token, user_id, profile["displayName"], "telegram")
    return {
        "token": token,
        "userId": user_id,
        "displayName": profile["displayName"],
        "mode": "telegram",
    }


@router.get("/profile")
def read_profile(session: dict = Depends(current_session), store: Store = Depends(get_store)) -> dict:
    return public_profile(store.load(session["userId"]))


@router.put("/profile")
def write_profile(
    body: ProfileIn,
    session: dict = Depends(current_session),
    store: Store = Depends(get_store),
) -> dict:
    state = store.load(session["userId"])
    state["balance"] = str(body.balance)
    state["incomes"] = [
        {
            "id": item.id or f"i-{uuid.uuid4().hex[:8]}",
            "title": item.title.strip(),
            "amount": str(item.amount),
            "dayOfMonth": item.dayOfMonth,
        }
        for item in body.incomes
    ]
    store.save(session["userId"], state)
    return public_profile(state)


@router.post("/demo/seed", status_code=204)
def seed_demo(session: dict = Depends(current_session), store: Store = Depends(get_store)) -> None:
    store.seed(session["userId"])


@router.delete("/dataset", status_code=204)
def clear_dataset(session: dict = Depends(current_session), store: Store = Depends(get_store)) -> None:
    store.clear(session["userId"])


@router.get("/transactions")
def list_transactions(
    session: dict = Depends(current_session), store: Store = Depends(get_store)
) -> list[dict]:
    return public_transactions(store.load(session["userId"]))


@router.post("/transactions/import")
def import_transactions(
    body: ImportIn,
    session: dict = Depends(current_session),
    store: Store = Depends(get_store),
) -> dict:
    state = store.load(session["userId"])
    imported = 0
    rejected: list[dict] = []
    warnings: list[str] = []
    existing = {(row["date"], row["amount"], row["merchant"].casefold()) for row in state["transactions"]}
    for index, row in enumerate(body.rows, start=1):
        message = _row_problem(row)
        if message:
            rejected.append({"row": index, "message": message})
            continue
        category = row.category if row.category in CATEGORIES else "other"
        if category != row.category:
            warnings.append(f"Строка {index}: неизвестная категория заменена на «другое».")
        amount = str(row.amount.quantize(Decimal("0.01")))
        key = (row.date.isoformat(), amount, row.merchant.strip().casefold())
        if key in existing:
            warnings.append(f"Строка {index}: такая операция уже есть, пропущена.")
            continue
        state["transactions"].append(
            {
                "id": f"t-{uuid.uuid4().hex[:8]}",
                "date": row.date.isoformat(),
                "amount": amount,
                "category": category,
                "merchant": row.merchant.strip(),
                "isRecurring": False,
            }
        )
        existing.add(key)
        imported += 1
    _refresh_recurring(state["transactions"])
    store.save(session["userId"], state)
    if imported == 0 and not rejected:
        warnings.append("Новых операций нет.")
    return {"imported": imported, "rejected": rejected, "warnings": warnings}


@router.get("/analysis/overview")
def overview(session: dict = Depends(current_session), store: Store = Depends(get_store)) -> dict:
    state = store.load(session["userId"])
    as_of = today()
    if not state["transactions"]:
        return _insufficient(_empty_overview(as_of), ["операции хотя бы за один месяц"], 0)
    raw = build_overview(state["transactions"], as_of)
    if not raw["_has_rows"]:
        return _insufficient(
            _empty_overview(as_of),
            ["операции за текущий месяц"],
            coverage_days(state["transactions"], as_of),
        )
    share = 0 if raw["_total_expense"] == 0 else round(float(raw["_recurring"] / raw["_total_expense"] * 100))
    payload = explained(
        _overview_public(raw),
        assumptions=[
            f"Период: {raw['periodFrom']} — {raw['periodTo']}.",
            "Регулярные — аренда, подписки, проезд и повтор из месяца в месяц.",
        ],
        calculation=[
            step("Расходы за период", "сумма операций со знаком минус", raw["_total_expense"]),
            step("из них регулярные", "операции с признаком «регулярный»", raw["_recurring"]),
            step("Доля регулярных, %", "регулярные / все расходы", share),
        ],
        limitations=COMMON_LIMITS,
        sufficient=True,
        missing=[],
        coverage_days=coverage_days(state["transactions"], as_of),
    )
    return payload


@router.get("/analysis/forecast")
def forecast(session: dict = Depends(current_session), store: Store = Depends(get_store)) -> dict:
    state = store.load(session["userId"])
    as_of = today()
    if state["balance"] is None:
        return _insufficient(
            _empty_forecast(as_of),
            ["текущий баланс"],
            coverage_days(state["transactions"], as_of),
        )
    raw = build_forecast(balance_of(state), state["incomes"], state["transactions"], as_of)
    assumptions = ["Обязательные платежи берутся только из регулярных операций, даты не выдумываются."]
    if raw["_planned_titles"]:
        assumptions.append("До конца месяца запланировано: " + ", ".join(raw["_planned_titles"]) + ".")
    else:
        assumptions.append("До конца месяца в регулярных операциях новых списаний нет.")
    if raw["_expected_titles"]:
        assumptions.append("Ещё ожидается: " + ", ".join(raw["_expected_titles"]) + ".")
    else:
        assumptions.append("Новых поступлений до конца месяца в профиле нет.")
    return explained(
        {
            "daysLeft": raw["daysLeft"],
            "expectedIncome": raw["expectedIncome"],
            "plannedExpenses": raw["plannedExpenses"],
            "projectedBalance": raw["projectedBalance"],
            "safeDailySpend": raw["safeDailySpend"],
            "verdict": raw["verdict"],
        },
        assumptions=assumptions,
        calculation=[
            step("Текущий баланс", "остаток, который вы указали", raw["_balance"]),
            step("Обязательные платежи", ", ".join(raw["_planned_titles"]) or "нет", raw["plannedExpenses"]),
            step("Остаток к концу месяца", "баланс + поступления − обязательные", raw["_projected"]),
            step("Можно тратить в день", f"остаток / {raw['daysLeft']} дн.", raw["_safe"]),
        ],
        limitations=COMMON_LIMITS,
        sufficient=True,
        missing=[],
        coverage_days=coverage_days(state["transactions"], as_of),
    )


@router.get("/analysis/runway")
def runway(session: dict = Depends(current_session), store: Store = Depends(get_store)) -> dict:
    state = store.load(session["userId"])
    as_of = today()
    missing = []
    if state["balance"] is None:
        missing.append("текущий баланс")
    if not state["incomes"]:
        missing.append("хотя бы одно регулярное поступление с днём месяца")
    if missing:
        return _insufficient(_empty_runway(as_of), missing, coverage_days(state["transactions"], as_of))
    raw = build_runway(balance_of(state) or D(0), state["incomes"], state["transactions"], as_of)
    nxt = raw["nextIncome"]
    return explained(
        _runway_public(raw),
        assumptions=[
            "Календарь идёт от сегодня до последнего известного платежа или поступления.",
            "Обязательные платежи стоят в те же дни месяца, что и регулярные операции.",
        ],
        calculation=[
            step("Текущий баланс", "остаток на счёте", balance_of(state) or D(0)),
            step(
                "Дней до поступления",
                nxt["title"] if nxt else "нет ближайшего дохода",
                nxt["daysUntil"] if nxt else 0,
            ),
            step(
                "Можно тратить в день",
                "свободные деньги до поступления / число дней",
                D(raw["todaySafeSpend"]),
            ),
            step(
                "Минимальный остаток",
                "после всех обязательных платежей на горизонте",
                D(raw["lowestBalance"]),
            ),
        ],
        limitations=COMMON_LIMITS,
        sufficient=True,
        missing=[],
        coverage_days=coverage_days(state["transactions"], as_of),
    )


@router.post("/analysis/impulse")
def impulse(
    body: ImpulseIn,
    session: dict = Depends(current_session),
    store: Store = Depends(get_store),
) -> dict:
    state = store.load(session["userId"])
    as_of = today()
    if state["balance"] is None:
        return _insufficient(
            _empty_impulse(body.amount),
            ["текущий баланс"],
            coverage_days(state["transactions"], as_of),
        )
    raw = build_impulse(
        balance_of(state) or D(0),
        state["incomes"],
        state["transactions"],
        state["goals"],
        as_of,
        body.amount,
    )
    return explained(
        _impulse_public(raw),
        assumptions=[
            "Покупка списывается сегодня, обязательные платежи остаются на своих датах.",
            "Поступления берутся из профиля.",
        ],
        calculation=[
            step("Покупка", "сумма, которую хотите потратить сегодня", body.amount),
            step(
                "Лимит в день до покупки",
                "свободные деньги / дни до поступления",
                D(raw["todaySafeSpendBefore"]),
            ),
            step("Лимит в день после покупки", "то же после списания", D(raw["todaySafeSpendAfter"])),
            step(
                "Минимальный остаток после покупки", "худший день на горизонте", D(raw["lowestBalanceAfter"])
            ),
        ],
        limitations=COMMON_LIMITS,
        sufficient=True,
        missing=[],
        coverage_days=coverage_days(state["transactions"], as_of),
    )


@router.get("/goals/{goal_id}/plan")
def goal_plan(
    goal_id: str, session: dict = Depends(current_session), store: Store = Depends(get_store)
) -> dict:
    state = store.load(session["userId"])
    goal = next((item for item in state["goals"] if item["id"] == goal_id), None)
    if goal is None:
        raise HTTPException(status_code=404, detail="Цель не найдена.")
    as_of = today()
    raw = build_goal_plan(goal, state["transactions"], as_of)
    if raw["_missing"]:
        return explained(
            _goal_public(raw),
            assumptions=[],
            calculation=[],
            sources=[],
            limitations=["Без срока нельзя честно назвать дату, когда цель будет достигнута."],
            sufficient=False,
            missing=raw["_missing"],
            coverage_days=coverage_days(state["transactions"], as_of),
        )
    if raw.get("_done"):
        text_formula = "уже накоплено не меньше суммы цели"
        pace = D(0)
    else:
        text_formula = f"{fmt_rub(raw['_remaining'])} / {raw['_days_left']} дн. до срока"
        pace = raw["_pace"]
    return explained(
        _goal_public(raw),
        assumptions=[
            "Темп — сколько откладывать в месяц, чтобы успеть к сроку. Это не обещание.",
        ],
        calculation=[
            step("Осталось накопить", "сумма цели − уже отложено", raw["_remaining"]),
            step("Нужно в месяц", text_formula, pace),
        ],
        limitations=COMMON_LIMITS,
        sufficient=True,
        missing=[],
        coverage_days=coverage_days(state["transactions"], as_of),
    )


@router.post("/goals", status_code=201)
def create_goal(
    body: GoalIn,
    session: dict = Depends(current_session),
    store: Store = Depends(get_store),
) -> dict:
    state = store.load(session["userId"])
    goal = _goal_record(f"g-{uuid.uuid4().hex[:8]}", body)
    state["goals"].append(goal)
    store.save(session["userId"], state)
    return _stored_goal_public(goal)


@router.patch("/goals/{goal_id}")
def update_goal(
    goal_id: str,
    body: GoalIn,
    session: dict = Depends(current_session),
    store: Store = Depends(get_store),
) -> dict:
    state = store.load(session["userId"])
    for index, goal in enumerate(state["goals"]):
        if goal["id"] == goal_id:
            updated = _goal_record(goal_id, body)
            state["goals"][index] = updated
            store.save(session["userId"], state)
            return _stored_goal_public(updated)
    raise HTTPException(status_code=404, detail="Цель не найдена.")


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(
    goal_id: str, session: dict = Depends(current_session), store: Store = Depends(get_store)
) -> None:
    state = store.load(session["userId"])
    remaining = [goal for goal in state["goals"] if goal["id"] != goal_id]
    if len(remaining) == len(state["goals"]):
        raise HTTPException(status_code=404, detail="Цель не найдена.")
    state["goals"] = remaining
    store.save(session["userId"], state)


@router.post("/ask")
def ask(body: AskIn, session: dict = Depends(current_session), store: Store = Depends(get_store)) -> dict:
    state = store.load(session["userId"])
    numeric = {
        "balance": balance_of(state),
        "incomes": state["incomes"],
        "goals": state["goals"],
        "transactions": state["transactions"],
    }
    return answer(body.question.strip(), body.scenarioId, numeric, today())


@router.get("/history")
def read_history(session: dict = Depends(current_session), store: Store = Depends(get_store)) -> list[dict]:
    state = store.load(session["userId"])
    return sorted(state["history"], key=lambda item: item["createdAt"], reverse=True)


@router.put("/history/{entry_id}")
def save_history(
    entry_id: str,
    body: dict,
    session: dict = Depends(current_session),
    store: Store = Depends(get_store),
) -> dict:
    if body.get("id") != entry_id:
        raise HTTPException(status_code=422, detail="Идентификатор в адресе и в теле не совпадает.")
    required = ("scenarioId", "title", "createdAt", "messages")
    if any(key not in body for key in required):
        raise HTTPException(status_code=422, detail="В истории не хватает полей диалога.")
    state = store.load(session["userId"])
    state["history"] = [item for item in state["history"] if item.get("id") != entry_id]
    state["history"].append(body)
    store.save(session["userId"], state)
    return body


@router.delete("/history", status_code=204)
def clear_history(session: dict = Depends(current_session), store: Store = Depends(get_store)) -> None:
    state = store.load(session["userId"])
    state["history"] = []
    store.save(session["userId"], state)


def _goal_record(goal_id: str, body: GoalIn) -> dict:
    return {
        "id": goal_id,
        "title": body.title.strip(),
        "targetAmount": str(body.targetAmount),
        "savedAmount": str(body.savedAmount),
        "deadline": body.deadline.isoformat() if body.deadline else None,
    }


def _stored_goal_public(goal: dict) -> dict:
    return {
        "id": goal["id"],
        "title": goal["title"],
        "targetAmount": float(D(goal["targetAmount"])),
        "savedAmount": float(D(goal["savedAmount"])),
        "deadline": goal["deadline"],
    }


def _goal_public(raw: dict) -> dict:
    return {
        "goalId": raw["goalId"],
        "monthlyPace": raw["monthlyPace"],
        "etaMonths": raw["etaMonths"],
        "etaDate": raw["etaDate"],
        "blockers": raw["blockers"],
    }


def _overview_public(raw: dict) -> dict:
    return {
        "periodFrom": raw["periodFrom"],
        "periodTo": raw["periodTo"],
        "totalIncome": raw["totalIncome"],
        "totalExpense": raw["totalExpense"],
        "recurringTotal": raw["recurringTotal"],
        "byCategory": raw["byCategory"],
        "anomalies": raw["anomalies"],
    }


def _runway_public(raw: dict) -> dict:
    return {
        "horizonTo": raw["horizonTo"],
        "nextIncome": raw["nextIncome"],
        "todaySafeSpend": raw["todaySafeSpend"],
        "lowestBalance": raw["lowestBalance"],
        "redDays": raw["redDays"],
        "days": raw["days"],
    }


def _impulse_public(raw: dict) -> dict:
    return {
        key: raw[key]
        for key in (
            "amount",
            "verdict",
            "hint",
            "todaySafeSpendBefore",
            "todaySafeSpendAfter",
            "redDaysBefore",
            "redDaysAfter",
            "lowestBalanceAfter",
            "waitUntil",
            "goalImpact",
            "daysAfter",
        )
    }


def _insufficient(result: dict, missing: list[str], coverage: int) -> dict:
    return explained(
        result,
        assumptions=[],
        calculation=[],
        limitations=COMMON_LIMITS,
        sufficient=False,
        missing=missing,
        coverage_days=coverage,
    )


def _empty_overview(as_of: date) -> dict:
    start = date(as_of.year, as_of.month, 1)
    return {
        "periodFrom": start.isoformat(),
        "periodTo": as_of.isoformat(),
        "totalIncome": 0,
        "totalExpense": 0,
        "recurringTotal": 0,
        "byCategory": [],
        "anomalies": [],
    }


def _empty_forecast(as_of: date) -> dict:
    if as_of.month == 12:
        month_end = date(as_of.year + 1, 1, 1)
    else:
        month_end = date(as_of.year, as_of.month + 1, 1)
    days_left = max((month_end - as_of).days - 1, 0)
    return {
        "daysLeft": days_left,
        "expectedIncome": 0,
        "plannedExpenses": 0,
        "projectedBalance": 0,
        "safeDailySpend": 0,
        "verdict": "shortfall",
    }


def _empty_runway(as_of: date) -> dict:
    return {
        "horizonTo": as_of.isoformat(),
        "nextIncome": None,
        "todaySafeSpend": 0,
        "lowestBalance": 0,
        "redDays": 0,
        "days": [],
    }


def _empty_impulse(amount: Decimal) -> dict:
    return {
        "amount": float(amount),
        "verdict": "wait",
        "hint": "",
        "todaySafeSpendBefore": 0,
        "todaySafeSpendAfter": 0,
        "redDaysBefore": 0,
        "redDaysAfter": 0,
        "lowestBalanceAfter": 0,
        "waitUntil": None,
        "goalImpact": None,
        "daysAfter": [],
    }


def _row_problem(row: ImportRowIn) -> str | None:
    if row.amount == 0:
        return "Сумма не может быть нулевой."
    if not row.merchant.strip():
        return "Не указано описание операции."
    compact = re.sub(r"\D", "", row.merchant)
    if CARD_RE.search(row.merchant) and 13 <= len(compact) <= 19:
        return "Похоже на номер карты. Такие данные загружать нельзя."
    return None


def _refresh_recurring(transactions: list[dict]) -> None:
    groups: dict[str, list[dict]] = {}
    for row in transactions:
        if D(row["amount"]) >= 0:
            continue
        key = " ".join(row["merchant"].casefold().split())
        groups.setdefault(key, []).append(row)
    for key, group in groups.items():
        months = {row["date"][:7] for row in group}
        keyword = any(word in key for word in RECURRING_WORDS)
        if keyword or len(months) >= 2:
            for row in group:
                row["isRecurring"] = True
