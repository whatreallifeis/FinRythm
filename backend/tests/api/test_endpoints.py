"""VF2: аналитика, цели, демо, импорт, помощник, история — формы ответов как у фронтенда."""

from datetime import date
from decimal import Decimal

import app.ai as ai
import app.core as core
import app.ingest as ingest
import pytest
from app.api.serialize import public_explained, to_json
from app.models import CalcStep, DataQuality, Explained, ImportResult, RejectedRow, SourceRef

from . import shapes
from .conftest import TODAY

ANALYSIS = [
    ("get", "/api/analysis/overview", None, shapes.overview),
    ("get", "/api/analysis/forecast", None, shapes.forecast),
    ("get", "/api/analysis/runway", None, shapes.runway),
    ("post", "/api/analysis/impulse", {"amount": 14900}, shapes.impulse),
]


def _seeded(client, auth) -> None:
    assert client.post("/api/demo/seed", headers=auth).status_code == 204


# ---------------------------------------------------------------- сериализация


def test_to_json_money_and_dates():
    value = {"a": Decimal("18430.50"), "b": [date(2026, 10, 5), None, True, 3], "c": {"d": Decimal("-1")}}
    assert to_json(value) == {"a": 18430.5, "b": ["2026-10-05", None, True, 3], "c": {"d": -1.0}}


def test_to_json_keeps_shares_precise():
    """#24: доля категории — не деньги, до копеек не округляется."""
    value = {"share": Decimal("0.3945"), "amount": Decimal("16540.00")}
    assert to_json(value) == {"share": 0.3945, "amount": 16540.0}


def test_public_explained_is_camel_case():
    payload = Explained(
        result={"todaySafeSpend": Decimal("650.4")},
        calculation=[
            CalcStep(label="Можно тратить в день", formula="7 800 ₽ / 12 дн.", value=Decimal("650.4"))
        ],
        sources=[SourceRef(title="Банк России", url="https://cbr.ru")],
        data_quality=DataQuality(sufficient=True, coverage_days=60),
    )
    body = public_explained(payload)
    shapes.check_explained(body, lambda result: None)
    assert body["result"] == {"todaySafeSpend": 650.4}
    assert body["dataQuality"] == {"sufficient": True, "missing": [], "coverageDays": 60}


# ---------------------------------------------------------------- демо


def test_demo_seed_fills_profile(client, auth):
    _seeded(client, auth)
    profile = client.get("/api/profile", headers=auth).json()
    assert profile["balance"] == 18430
    assert {item["title"] for item in profile["incomes"]} >= {"Стипендия", "Подработка"}
    assert profile["goals"]
    rows = client.get("/api/transactions", headers=auth).json()
    assert rows
    assert rows == sorted(rows, key=lambda row: row["date"], reverse=True)
    for row in rows:
        assert set(row) == {"id", "date", "amount", "category", "merchant", "isRecurring"}
        assert row["category"] in shapes.CATEGORIES


def test_demo_seed_keeps_history(client, auth):
    entry = {
        "id": "h-1",
        "scenarioId": "free",
        "title": "Q",
        "createdAt": "2026-09-26T10:00:00Z",
        "messages": [],
    }
    client.put("/api/history/h-1", json=entry, headers=auth)
    _seeded(client, auth)
    assert [item["id"] for item in client.get("/api/history", headers=auth).json()] == ["h-1"]


# ---------------------------------------------------------------- аналитика


@pytest.mark.parametrize(("method", "path", "body", "check"), ANALYSIS)
def test_analysis_shapes_on_demo(client, auth, method, path, body, check):
    _seeded(client, auth)
    response = getattr(client, method)(path, headers=auth, **({"json": body} if body else {}))
    assert response.status_code == 200
    shapes.check_explained(response.json(), check)


@pytest.mark.parametrize(("method", "path", "body", "check"), ANALYSIS)
def test_analysis_shapes_on_empty_profile(client, auth, method, path, body, check):
    response = getattr(client, method)(path, headers=auth, **({"json": body} if body else {}))
    assert response.status_code == 200
    shapes.check_explained(response.json(), check)
    assert response.json()["dataQuality"]["sufficient"] is False


@pytest.mark.parametrize(("method", "path", "body", "check"), ANALYSIS)
def test_analysis_requires_login(client, method, path, body, check):
    response = getattr(client, method)(path, **({"json": body} if body else {}))
    assert response.status_code == 401


def test_analysis_uses_stub_when_core_has_no_function(client, auth, monkeypatch):
    monkeypatch.delattr(core, "build_runway", raising=False)
    body = client.get("/api/analysis/runway", headers=auth).json()
    shapes.check_explained(body, shapes.runway)
    assert body["dataQuality"]["sufficient"] is False
    assert "не подключён" in body["dataQuality"]["missing"][0]


def test_analysis_calls_core_with_state_and_today(client, auth, monkeypatch):
    seen = {}

    def fake_runway(state, as_of):
        seen.update(balance=state.balance, as_of=as_of)
        return Explained(
            result={
                "horizonTo": date(2026, 10, 5),
                "nextIncome": {
                    "date": date(2026, 10, 5),
                    "title": "Стипендия",
                    "amount": Decimal("8000"),
                    "daysUntil": 9,
                },
                "todaySafeSpend": Decimal("650.50"),
                "lowestBalance": Decimal("1200"),
                "redDays": 0,
                "days": [
                    {
                        "date": date(2026, 9, 27),
                        "events": [{"title": "Аренда", "amount": Decimal("-5000")}],
                        "balance": Decimal("13430"),
                        "status": "ok",
                    }
                ],
            },
            calculation=[CalcStep(label="Можно тратить в день", formula="…", value=Decimal("650.50"))],
            data_quality=DataQuality(sufficient=True, coverage_days=61),
        )

    monkeypatch.setattr(core, "build_runway", fake_runway, raising=False)
    client.put("/api/profile", json={"balance": 18430, "incomes": []}, headers=auth)
    body = client.get("/api/analysis/runway", headers=auth).json()
    shapes.check_explained(body, shapes.runway)
    assert seen == {"balance": Decimal("18430"), "as_of": TODAY}
    assert body["result"]["todaySafeSpend"] == 650.5
    assert body["result"]["nextIncome"]["date"] == "2026-10-05"
    assert body["result"]["days"][0]["events"][0]["amount"] == -5000


def test_impulse_passes_amount_as_decimal(client, auth, monkeypatch):
    seen = {}

    def fake(state, amount, as_of):
        seen["amount"] = amount
        from app.api import stubs

        return stubs.check_impulse(state, amount, as_of)

    monkeypatch.setattr(core, "check_impulse", fake, raising=False)
    client.post("/api/analysis/impulse", json={"amount": 14900.5}, headers=auth)
    assert seen["amount"] == Decimal("14900.5")


@pytest.mark.parametrize("amount", [0, -5, "много"])
def test_impulse_validation(client, auth, amount):
    response = client.post("/api/analysis/impulse", json={"amount": amount}, headers=auth)
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "amount"


# ---------------------------------------------------------------- цели


def test_goal_crud(client, auth):
    draft = {"title": "Ноутбук", "targetAmount": 75000, "savedAmount": 21000, "deadline": "2027-02-01"}
    created = client.post("/api/goals", json=draft, headers=auth)
    assert created.status_code == 201
    goal = created.json()
    assert goal == {"id": goal["id"], **{**draft, "targetAmount": 75000.0, "savedAmount": 21000.0}}
    updated = client.patch(
        f"/api/goals/{goal['id']}", json={**draft, "savedAmount": 30000, "deadline": None}, headers=auth
    ).json()
    assert updated["savedAmount"] == 30000 and updated["deadline"] is None
    assert client.get("/api/profile", headers=auth).json()["goals"] == [updated]
    assert client.delete(f"/api/goals/{goal['id']}", headers=auth).status_code == 204
    assert client.get("/api/profile", headers=auth).json()["goals"] == []


def test_goal_not_found(client, auth):
    draft = {"title": "Х", "targetAmount": 1, "savedAmount": 0, "deadline": None}
    for response in (
        client.patch("/api/goals/nope", json=draft, headers=auth),
        client.delete("/api/goals/nope", headers=auth),
        client.get("/api/goals/nope/plan", headers=auth),
    ):
        assert response.status_code == 404
        assert response.json()["error"]["message"] == "Цель не найдена."


def test_goal_saved_above_target_is_422(client, auth):
    draft = {"title": "Х", "targetAmount": 100, "savedAmount": 101, "deadline": None}
    response = client.post("/api/goals", json=draft, headers=auth)
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "Накоплено не может быть больше суммы цели"


def test_goal_plan_shape(client, auth):
    _seeded(client, auth)
    goal_id = client.get("/api/profile", headers=auth).json()["goals"][0]["id"]
    response = client.get(f"/api/goals/{goal_id}/plan", headers=auth)
    assert response.status_code == 200
    shapes.check_explained(response.json(), shapes.goal_plan)


# ---------------------------------------------------------------- импорт


def test_import_calls_ingest_and_saves(client, auth, monkeypatch):
    def fake(state, rows, as_of):
        from app.models import Operation

        added = [
            Operation(id=f"t-{i}", date=row.date, amount=row.amount, category="food", merchant=row.merchant)
            for i, row in enumerate(rows)
        ]
        state.transactions.extend(added)
        result = ImportResult(
            imported=len(added), rejected=[RejectedRow(row=3, message="Пустая сумма")], warnings=["w"]
        )
        return state, result

    monkeypatch.setattr(ingest, "apply_import", fake, raising=False)
    rows = [
        {"date": "2026-09-20", "amount": -349.9, "category": "food", "merchant": "Пятёрочка"},
        {"date": "2026-09-21", "amount": 8000, "category": "other", "merchant": "Стипендия"},
    ]
    response = client.post("/api/transactions/import", json={"rows": rows}, headers=auth)
    assert response.status_code == 200
    assert response.json() == {
        "imported": 2,
        "rejected": [{"row": 3, "message": "Пустая сумма"}],
        "warnings": ["w"],
    }
    saved = client.get("/api/transactions", headers=auth).json()
    assert [row["amount"] for row in saved] == [8000.0, -349.9]


def test_import_stub_shape(client, auth, monkeypatch):
    monkeypatch.delattr(ingest, "apply_import", raising=False)
    rows = [{"date": "2026-09-20", "amount": -1, "category": "food", "merchant": "x"}]
    body = client.post("/api/transactions/import", json={"rows": rows}, headers=auth).json()
    assert set(body) == {"imported", "rejected", "warnings"}
    assert body["imported"] == 0 and body["warnings"]


def test_import_bad_date_rejects_only_that_row(client, auth):
    """#52: неверная или несуществующая дата не отклоняет весь файл."""
    rows = [
        {"date": "2026-09-20", "amount": -540, "category": "food", "merchant": "Супермаркет"},
        {"date": "2026-02-30", "amount": -100, "category": "food", "merchant": "Кафе"},
        {"date": "20.09.2026", "amount": -1, "category": "food", "merchant": "x"},
    ]
    response = client.post("/api/transactions/import", json={"rows": rows}, headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 1
    assert body["rejected"] == [
        {"row": 2, "message": "Такой даты нет в календаре: 2026-02-30"},
        {"row": 3, "message": "Дата в формате ГГГГ-ММ-ДД"},
    ]
    assert [row["merchant"] for row in client.get("/api/transactions", headers=auth).json()] == [
        "Супермаркет"
    ]


def test_import_bad_date_uses_file_row_and_keeps_ingest_numbers(client, auth):
    rows = [
        {"date": "2026-09-31", "amount": -100, "category": "food", "merchant": "Кафе", "row": 2},
        {"date": "2026-09-27", "amount": -540, "category": "food", "merchant": "Будущее", "row": 5},
        {"date": "2026-09-20", "amount": -200, "category": "кафе", "merchant": "Кофейня", "row": 9},
    ]
    body = client.post("/api/transactions/import", json={"rows": rows}, headers=auth).json()
    assert [item["row"] for item in body["rejected"]] == [2, 5]
    assert body["warnings"][0].startswith("Строка 9:")


def test_import_too_many_rows_is_422(client, auth):
    rows = [{"date": "2026-09-20", "amount": -1, "category": "food", "merchant": "x"}] * 5001
    response = client.post("/api/transactions/import", json={"rows": rows}, headers=auth)
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "rows"


# ---------------------------------------------------------------- помощник


@pytest.mark.parametrize("scenario", ["expenses", "budget", "glossary", "impulse", "free"])
def test_ask_shape_for_every_scenario(client, auth, scenario):
    _seeded(client, auth)
    response = client.post(
        "/api/ask", json={"question": "Хватит ли до стипендии?", "scenarioId": scenario}, headers=auth
    )
    assert response.status_code == 200
    shapes.check_explained(response.json(), shapes.ask_answer)


def test_ask_passes_everything_to_ai(client, auth, monkeypatch):
    seen = {}

    async def fake_ask(question, scenario_id, state, as_of, *, llm, kb):
        seen.update(question=question, scenario=scenario_id, as_of=as_of, llm=llm)
        return Explained(result={"text": "Ответ"}, data_quality=DataQuality(sufficient=True))

    monkeypatch.setattr(ai, "ask", fake_ask, raising=False)
    body = client.post(
        "/api/ask", json={"question": "  Вопрос  ", "scenarioId": "impulse"}, headers=auth
    ).json()
    assert body["result"] == {"text": "Ответ"}
    assert seen["question"] == "Вопрос" and seen["scenario"] == "impulse" and seen["as_of"] == TODAY
    assert seen["llm"] is client.app.state.llm is not None


def test_ask_sync_implementation_also_works(client, auth, monkeypatch):
    def fake_ask(question, scenario_id, state, as_of, *, llm, kb):
        return Explained(result={"text": "Синхронно"}, data_quality=DataQuality(sufficient=True))

    monkeypatch.setattr(ai, "ask", fake_ask, raising=False)
    body = client.post("/api/ask", json={"question": "Q", "scenarioId": "free"}, headers=auth).json()
    assert body["result"]["text"] == "Синхронно"


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"question": "Q", "scenarioId": "poker"}, "scenarioId"),
        ({"question": "", "scenarioId": "free"}, "question"),
        ({"question": "x" * 1001, "scenarioId": "free"}, "question"),
    ],
)
def test_ask_validation(client, auth, body, field):
    response = client.post("/api/ask", json=body, headers=auth)
    assert response.status_code == 422
    assert response.json()["error"]["field"] == field


def test_ask_llm_unavailable_is_503(client, auth, monkeypatch):
    class LLMUnavailable(Exception):
        pass

    async def failing(*args, **kwargs):
        raise LLMUnavailable("timeout")

    monkeypatch.setattr(ai, "LLMUnavailable", LLMUnavailable, raising=False)
    monkeypatch.setattr(ai, "ask", failing, raising=False)
    response = client.post("/api/ask", json={"question": "Q", "scenarioId": "free"}, headers=auth)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_unavailable"


def test_ask_without_llm_is_503(client, auth):
    client.app.state.llm = None
    response = client.post("/api/ask", json={"question": "Q", "scenarioId": "free"}, headers=auth)
    assert response.status_code == 503


def test_ask_rate_limit(client, auth):
    client.app.state.ask_limiter.per_minute = 2
    body = {"question": "Q", "scenarioId": "free"}
    assert [client.post("/api/ask", json=body, headers=auth).status_code for _ in range(3)] == [200, 200, 429]
    assert client.post("/api/ask", json=body, headers=auth).json()["error"]["code"] == "rate_limited"


# ---------------------------------------------------------------- история


def _entry(entry_id: str, created: str) -> dict:
    answer = {
        "result": {"text": "Ответ"},
        "assumptions": [],
        "calculation": [],
        "sources": [],
        "limitations": [],
        "dataQuality": {"sufficient": True, "missing": [], "coverageDays": 0},
    }
    return {
        "id": entry_id,
        "scenarioId": "budget",
        "title": "Хватит ли до стипендии?",
        "createdAt": created,
        "messages": [{"role": "user", "text": "Хватит ли?"}, {"role": "assistant", "answer": answer}],
    }


def test_history_roundtrip_sorted_and_cleared(client, auth):
    old, new = _entry("h-1", "2026-09-25T10:00:00Z"), _entry("h-2", "2026-09-26T10:00:00Z")
    assert client.put("/api/history/h-1", json=old, headers=auth).json() == old
    client.put("/api/history/h-2", json=new, headers=auth)
    changed = {**old, "title": "Новый заголовок"}
    client.put("/api/history/h-1", json=changed, headers=auth)
    assert client.get("/api/history", headers=auth).json() == [new, changed]
    assert client.delete("/api/history", headers=auth).status_code == 204
    assert client.get("/api/history", headers=auth).json() == []


def test_history_id_mismatch_is_422(client, auth):
    response = client.put("/api/history/h-9", json=_entry("h-1", "x"), headers=auth)
    assert response.status_code == 422


def test_root_redirects_to_docs(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/docs"


# ---------------------------------------------------------------- исправления по issue


def test_import_reports_file_row_numbers(client, auth, monkeypatch):
    """#36: если фронтенд прислал номер строки файла, ошибки и предупреждения ссылаются на него."""

    def fake(state, rows, as_of):
        result = ImportResult(
            imported=1,
            rejected=[RejectedRow(row=2, message="Дата операции в будущем")],
            warnings=["Строка 1: неизвестная категория «кафе» заменена на «другое».", "Новых операций нет."],
        )
        return state, result

    monkeypatch.setattr(ingest, "apply_import", fake, raising=False)
    rows = [
        {"date": "2026-09-20", "amount": -100, "category": "кафе", "merchant": "Кофейня", "row": 4},
        {"date": "2026-09-27", "amount": -540, "category": "food", "merchant": "Супермаркет", "row": 7},
    ]
    body = client.post("/api/transactions/import", json={"rows": rows}, headers=auth).json()
    assert body["rejected"] == [{"row": 7, "message": "Дата операции в будущем"}]
    assert body["warnings"][0].startswith("Строка 4:")
    assert body["warnings"][1] == "Новых операций нет."


def test_import_without_file_rows_keeps_list_numbers(client, auth, monkeypatch):
    def fake(state, rows, as_of):
        return state, ImportResult(imported=0, rejected=[RejectedRow(row=1, message="Нулевая сумма")])

    monkeypatch.setattr(ingest, "apply_import", fake, raising=False)
    rows = [{"date": "2026-09-20", "amount": 0, "category": "food", "merchant": "x"}]
    body = client.post("/api/transactions/import", json={"rows": rows}, headers=auth).json()
    assert body["rejected"] == [{"row": 1, "message": "Нулевая сумма"}]


def test_import_with_real_ingest_uses_file_rows(client, auth):
    rows = [
        {"date": "2026-09-20", "amount": -100, "category": "food", "merchant": "Кофейня", "row": 2},
        {"date": "2026-09-27", "amount": -540, "category": "food", "merchant": "Супермаркет", "row": 3},
    ]
    body = client.post("/api/transactions/import", json={"rows": rows}, headers=auth).json()
    assert body["imported"] == 1
    assert [item["row"] for item in body["rejected"]] == [3]


def test_broken_json_has_no_field(client, auth):
    """#30: у битого JSON в loc позиция символа, а не поле."""
    response = client.post(
        "/api/transactions/import",
        content=b'{"rows": [',
        headers={**auth, "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    expected = {"code": "validation_error", "message": "Некорректный JSON", "field": None}
    assert response.json()["error"] == expected


def test_null_instead_of_text_is_explained(client, auth):
    """#30: null в текстовом поле — понятный текст, а не общий."""
    rows = [{"date": "2026-09-01", "amount": -1, "category": "food", "merchant": None}]
    response = client.post("/api/transactions/import", json={"rows": rows}, headers=auth)
    assert response.json()["error"] == {
        "code": "validation_error",
        "message": "Нужен текст",
        "field": "rows.0.merchant",
    }


def test_overview_share_is_not_rounded_to_cents(client, auth):
    """#24 на настоящем core: доли в обзоре не обрезаются до сотых."""
    _seeded(client, auth)
    overview = client.get("/api/analysis/overview", headers=auth).json()["result"]
    shares = [item["share"] for item in overview["byCategory"]]
    assert shares
    assert any(round(share, 2) != share for share in shares)
    assert abs(sum(shares) - 1) < 0.001
