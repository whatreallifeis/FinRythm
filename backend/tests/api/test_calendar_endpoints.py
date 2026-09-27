"""Календарь и правки пользователя: готовая выписка, день календаря, автоплатежи, переименования."""

import csv
from pathlib import Path

import pytest

PRESETS = Path(__file__).resolve().parents[3] / "frontend" / "src" / "features" / "import" / "presets"


def rows_of(name: str) -> list[dict]:
    """Строки CSV в той форме, в какой их присылает фронтенд после разбора."""
    with (PRESETS / f"{name}.csv").open(encoding="utf-8") as file:
        return [
            {**row, "amount": float(row["amount"]), "row": index}
            for index, row in enumerate(csv.DictReader(file), start=2)
        ]


@pytest.fixture
def worker(client, auth):
    response = client.put("/api/dataset", json={"rows": rows_of("worker"), "balance": 21000}, headers=auth)
    assert response.status_code == 200
    return response.json()


def test_dataset_replaces_everything_and_finds_regular(client, auth, worker):
    assert worker["imported"] == 66 and worker["rejected"] == []
    assert "регулярных платежей: 5, регулярных поступлений: 2" in worker["warnings"][-1]
    profile = client.get("/api/profile", headers=auth).json()
    assert profile["balance"] == 21000
    assert [i["title"] for i in profile["incomes"]] == [
        "Аванс. ООО Енисей Сервис",
        "Зарплата. ООО Енисей Сервис",
    ]
    assert [a["dayOfMonth"] for a in profile["autopayments"]] == [1, 5, 8, 14, 22]
    runway = client.get("/api/analysis/runway", headers=auth).json()
    assert runway["dataQuality"]["sufficient"] and runway["result"]["todaySafeSpend"] == 79


def test_dataset_clears_goals_and_history(client, auth):
    client.post("/api/demo/seed", headers=auth)
    client.put("/api/dataset", json={"rows": rows_of("student"), "balance": 4092}, headers=auth)
    assert client.get("/api/profile", headers=auth).json()["goals"] == []
    assert client.get("/api/history", headers=auth).json() == []


def test_future_day_has_planned_payment_and_note(client, auth, worker):
    day = client.get("/api/calendar/2026-10-01", headers=auth).json()
    result = day["result"]
    assert result["kind"] == "future"
    [rent] = result["operations"]
    assert rent["ref"]["kind"] == "autopayment" and rent["ref"]["id"].startswith("rec-")
    assert rent["amount"] == -17000 and rent["isRecurring"]
    assert result["balance"] == 4000 and result["status"] == "ok"
    assert "самый крупный обязательный платёж" in result["note"]


def test_past_day_shows_statement_and_no_note_for_one_offs(client, auth, worker):
    result = client.get("/api/calendar/2026-09-12", headers=auth).json()["result"]
    assert result["kind"] == "past"
    assert [op["title"] for op in result["operations"]] == ["M.VIDEO Krasnoyarsk RU"]
    assert result["note"] is None
    assert result["typicalSpend"] is not None


def test_rename_recurring_transaction_renames_series_and_calendar(client, auth, worker):
    ops = client.get("/api/transactions", headers=auth).json()
    rent = next(op for op in ops if op["merchant"].startswith("Внешний перевод по номеру телефона +7"))
    response = client.patch(
        f"/api/transactions/{rent['id']}", json={"merchant": "Аренда квартиры"}, headers=auth
    )
    assert response.status_code == 200 and response.json()["merchant"] == "Аренда квартиры"
    renamed = [
        op
        for op in client.get("/api/transactions", headers=auth).json()
        if op["merchant"] == "Аренда квартиры"
    ]
    assert len(renamed) == 2  # август и сентябрь
    day = client.get("/api/calendar/2026-10-01", headers=auth).json()["result"]
    assert day["operations"][0]["title"] == "Аренда квартиры"
    assert "не менялась с 1 августа" in day["note"]  # история платежа сохранилась


def test_rename_one_off_changes_only_it(client, auth, worker):
    ops = client.get("/api/transactions", headers=auth).json()
    taxi = [op for op in ops if op["merchant"] == "Яндекс Go"]
    client.patch(f"/api/transactions/{taxi[0]['id']}", json={"merchant": "Такси домой"}, headers=auth)
    after = [op["merchant"] for op in client.get("/api/transactions", headers=auth).json()]
    assert after.count("Такси домой") == 1 and after.count("Яндекс Go") == len(taxi) - 1


def test_manual_autopayment_lifecycle(client, auth, worker):
    body = {"title": "Спортзал", "amount": 2500, "dayOfMonth": 20, "category": "health"}
    created = client.post("/api/autopayments", json=body, headers=auth)
    assert created.status_code == 201
    bill = created.json()
    assert bill["id"].startswith("a-") and bill["dayOfMonth"] == 20

    day = client.get("/api/calendar/2026-10-20", headers=auth).json()["result"]
    assert [op["title"] for op in day["operations"]] == ["Спортзал"]

    renamed = client.patch(f"/api/autopayments/{bill['id']}", json={"title": "Фитнес"}, headers=auth)
    assert renamed.json()["title"] == "Фитнес"
    assert client.delete(f"/api/autopayments/{bill['id']}", headers=auth).status_code == 204
    titles = [a["title"] for a in client.get("/api/profile", headers=auth).json()["autopayments"]]
    assert "Фитнес" not in titles


def test_delete_detected_autopayment_removes_it_from_calendar(client, auth, worker):
    profile = client.get("/api/profile", headers=auth).json()
    plus = next(a for a in profile["autopayments"] if a["title"] == "Яндекс Плюс")
    assert client.delete(f"/api/autopayments/{plus['id']}", headers=auth).status_code == 204
    titles = [a["title"] for a in client.get("/api/profile", headers=auth).json()["autopayments"]]
    assert "Яндекс Плюс" not in titles
    assert client.delete(f"/api/autopayments/{plus['id']}", headers=auth).status_code == 404


def test_rename_income_renames_its_deposits(client, auth, worker):
    income = client.get("/api/profile", headers=auth).json()["incomes"][1]
    response = client.patch(f"/api/incomes/{income['id']}", json={"title": "Зарплата"}, headers=auth)
    assert response.json()["title"] == "Зарплата"
    deposits = [
        op for op in client.get("/api/transactions", headers=auth).json() if op["merchant"] == "Зарплата"
    ]
    assert len(deposits) == 2 and all(op["isRecurring"] for op in deposits)


def test_not_found_and_validation(client, auth, worker):
    assert client.patch("/api/transactions/nope", json={"merchant": "x"}, headers=auth).status_code == 404
    assert client.patch("/api/incomes/nope", json={"title": "x"}, headers=auth).status_code == 404
    assert client.patch("/api/autopayments/nope", json={"title": "x"}, headers=auth).status_code == 404
    bad = {"title": "", "amount": -1, "dayOfMonth": 40}
    assert client.post("/api/autopayments", json=bad, headers=auth).status_code == 422
    assert client.get("/api/calendar/2026-13-01", headers=auth).status_code == 422
