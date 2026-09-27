"""Календарь на главной и правки пользователя (фронтенд ruina696, ветка frontAND).

GET    /api/calendar/{date}          — день: операции, обычные траты, остаток, справка помощника
PUT    /api/dataset                  — новая выписка целиком: операции, регулярное, баланс
PATCH  /api/transactions/{id}        — переименовать операцию (регулярную — всю серию)
POST   /api/autopayments             — добавить автоплатёж вручную
PATCH  /api/autopayments/{id}        — переименовать автоплатёж
DELETE /api/autopayments/{id}        — удалить автоплатёж
PATCH  /api/incomes/{id}             — переименовать регулярное поступление

Автоплатёж бывает двух видов: найденный в выписке (id «rec-…», это регулярные расходы по операциям)
и добавленный вручную. Переименование найденного переименовывает его операции; удаление снимает с них
признак «регулярный» — платёж пропадает из календаря.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api import engine
from app.api.deps import current_session, get_store, get_today
from app.api.schemas import AutopaymentIn, DatasetIn, RenameIn, TransactionRenameIn
from app.api.serialize import public_autopayment, public_explained, public_income, public_operation, to_json
from app.core.runway_calendar import bill_id, bills_of, normalize_merchant
from app.models import AutopaymentRule, ImportRow, UserState
from app.storage import Session, Store

router = APIRouter()


@router.get("/calendar/{day}")
async def calendar_day(
    day: date,
    request: Request,
    session: Session = Depends(current_session),
    store: Store = Depends(get_store),
    today: date = Depends(get_today),
) -> dict:
    insight = engine.build_day_insight(store.load(session.user_id), day, today)
    return public_explained(await engine.polish_day_note(insight, llm=request.app.state.llm))


@router.put("/dataset")
def replace_dataset(
    body: DatasetIn,
    session: Session = Depends(current_session),
    store: Store = Depends(get_store),
    today: date = Depends(get_today),
) -> dict:
    """Готовая выписка: прежние операции, автоплатежи, цели и история заменяются."""
    rows = [
        ImportRow(
            date=row.date, amount=row.amount, category=row.category, merchant=row.merchant, row=row.row or i
        )
        for i, row in enumerate(body.rows, start=1)
    ]
    state, result = engine.replace_dataset(rows, body.balance, today)
    store.save(session.user_id, state)
    return to_json(result)


def _rename_series(state: UserState, old_title: str, new_title: str, *, income: bool) -> None:
    """Регулярная серия переименовывается целиком, чтобы справка не потеряла историю платежа."""
    key = normalize_merchant(old_title)
    for index, op in enumerate(state.transactions):
        same_sign = op.amount > 0 if income else op.amount < 0
        if same_sign and (op.is_recurring or income) and normalize_merchant(op.merchant) == key:
            state.transactions[index] = op.model_copy(update={"merchant": new_title})


@router.patch("/transactions/{op_id}")
def rename_transaction(
    op_id: str,
    body: TransactionRenameIn,
    session: Session = Depends(current_session),
    store: Store = Depends(get_store),
) -> dict:
    state = store.load(session.user_id)
    op = next((item for item in state.transactions if item.id == op_id), None)
    if op is None:
        raise HTTPException(status_code=404, detail="Операция не найдена.")
    title = body.merchant.strip()
    income_rule = next(
        (inc for inc in state.incomes if normalize_merchant(inc.title) == normalize_merchant(op.merchant)),
        None,
    )
    if op.is_recurring or (op.amount > 0 and income_rule):
        _rename_series(state, op.merchant, title, income=op.amount > 0)
        if income_rule and op.amount > 0:
            state.incomes = [
                inc.model_copy(update={"title": title}) if inc.id == income_rule.id else inc
                for inc in state.incomes
            ]
        state.autopayments = [
            rule.model_copy(update={"title": title})
            if op.amount < 0 and normalize_merchant(rule.title) == normalize_merchant(op.merchant)
            else rule
            for rule in state.autopayments
        ]
    else:
        state.transactions = [
            item.model_copy(update={"merchant": title}) if item.id == op_id else item
            for item in state.transactions
        ]
    store.save(session.user_id, state)
    return public_operation(next(item for item in state.transactions if item.id == op_id))


@router.post("/autopayments", status_code=201)
def create_autopayment(
    body: AutopaymentIn, session: Session = Depends(current_session), store: Store = Depends(get_store)
) -> dict:
    state = store.load(session.user_id)
    rule = AutopaymentRule(
        id=f"a-{uuid.uuid4().hex[:8]}",
        title=body.title.strip(),
        amount=body.amount,
        day_of_month=body.day_of_month,
        category=body.category,
    )
    state.autopayments.append(rule)
    store.save(session.user_id, state)
    return public_autopayment(next(b for b in bills_of(state) if b.id == rule.id))


def _find_bill(state: UserState, bill: str):
    found = next((item for item in bills_of(state) if item.id == bill), None)
    if found is None:
        raise HTTPException(status_code=404, detail="Автоплатёж не найден.")
    return found


@router.patch("/autopayments/{bill}")
def rename_autopayment(
    bill: str, body: RenameIn, session: Session = Depends(current_session), store: Store = Depends(get_store)
) -> dict:
    state = store.load(session.user_id)
    found = _find_bill(state, bill)
    title = body.title.strip()
    if found.source == "manual":
        state.autopayments = [
            rule.model_copy(update={"title": title}) if rule.id == bill else rule
            for rule in state.autopayments
        ]
    _rename_series(state, found.title, title, income=False)
    store.save(session.user_id, state)
    new_id = bill if found.source == "manual" else bill_id(title)
    return public_autopayment(next(b for b in bills_of(state) if b.id == new_id))


@router.delete("/autopayments/{bill}", status_code=204)
def delete_autopayment(
    bill: str, session: Session = Depends(current_session), store: Store = Depends(get_store)
) -> Response:
    state = store.load(session.user_id)
    found = _find_bill(state, bill)
    if found.source == "manual":
        state.autopayments = [rule for rule in state.autopayments if rule.id != bill]
    else:
        key = normalize_merchant(found.title)
        state.transactions = [
            op.model_copy(update={"is_recurring": False})
            if op.is_recurring and op.amount < 0 and normalize_merchant(op.merchant) == key
            else op
            for op in state.transactions
        ]
    store.save(session.user_id, state)
    return Response(status_code=204)


@router.patch("/incomes/{income_id}")
def rename_income(
    income_id: str,
    body: RenameIn,
    session: Session = Depends(current_session),
    store: Store = Depends(get_store),
) -> dict:
    state = store.load(session.user_id)
    income = next((inc for inc in state.incomes if inc.id == income_id), None)
    if income is None:
        raise HTTPException(status_code=404, detail="Поступление не найдено.")
    title = body.title.strip()
    _rename_series(state, income.title, title, income=True)
    state.incomes = [
        inc.model_copy(update={"title": title}) if inc.id == income_id else inc for inc in state.incomes
    ]
    store.save(session.user_id, state)
    return public_income(next(inc for inc in state.incomes if inc.id == income_id))
