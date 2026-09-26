"""Наполнение данными: демо-набор и импорт операций (CSV разбирает фронтенд, присылает строки)."""

import re
from datetime import date

from fastapi import APIRouter, Depends, Response

from app.api import engine
from app.api.deps import current_session, get_store, get_today
from app.api.schemas import ImportIn, ImportRowIn
from app.api.serialize import to_json
from app.models import ImportResult, ImportRow, RejectedRow
from app.storage import Session, Store

router = APIRouter()


@router.post("/demo/seed", status_code=204)
def seed_demo(session: Session = Depends(current_session), store: Store = Depends(get_store)) -> Response:
    history = store.load(session.user_id).history
    state = engine.load_demo_state()
    state.history = history  # сохранённые диалоги не теряем
    store.save(session.user_id, state)
    return Response(status_code=204)


@router.post("/transactions/import")
def import_transactions(
    body: ImportIn,
    session: Session = Depends(current_session),
    store: Store = Depends(get_store),
    today: date = Depends(get_today),
) -> dict:
    rows, bad_dates = _parse_dates(body.rows)
    state, result = engine.apply_import(store.load(session.user_id), rows, today)
    store.save(session.user_id, state)
    result = _file_rows(result, rows)
    rejected = sorted([*bad_dates, *result.rejected], key=lambda item: item.row)
    return to_json(result.model_copy(update={"rejected": rejected}))


ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_dates(rows: list[ImportRowIn]) -> tuple[list[ImportRow], list[RejectedRow]]:
    """Строки с неверной или несуществующей датой — в отказы со своим номером, остальные — в ingest.

    У каждой переданной дальше строки есть row (номер файла или место в присланном списке),
    поэтому _file_rows вернёт номера ingest к нумерации пользователя.
    """
    good: list[ImportRow] = []
    bad: list[RejectedRow] = []
    for index, item in enumerate(rows, start=1):
        row = item.row or index
        text = item.date.strip()
        if not ISO_DATE.match(text):
            bad.append(RejectedRow(row=row, message="Дата в формате ГГГГ-ММ-ДД"))
            continue
        try:
            day = date.fromisoformat(text)
        except ValueError:
            bad.append(RejectedRow(row=row, message=f"Такой даты нет в календаре: {text}"))
            continue
        good.append(
            ImportRow(date=day, amount=item.amount, category=item.category, merchant=item.merchant, row=row)
        )
    return good, bad


LIST_ROW = re.compile(r"^Строка (\d+):")


def _file_rows(result: ImportResult, rows: list[ImportRow]) -> ImportResult:
    """ingest нумерует строки присланного списка с 1; фронтенд может прислать номер строки файла (#36)."""

    def file_row(index: int) -> int:
        if 1 <= index <= len(rows) and rows[index - 1].row is not None:
            return rows[index - 1].row
        return index

    rejected = [item.model_copy(update={"row": file_row(item.row)}) for item in result.rejected]

    def renumber(text: str) -> str:
        return LIST_ROW.sub(lambda m: f"Строка {file_row(int(m.group(1)))}:", text)

    warnings = [renumber(text) for text in result.warnings]
    return result.model_copy(update={"rejected": rejected, "warnings": warnings})
