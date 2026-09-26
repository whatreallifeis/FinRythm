"""Образцы data/samples/: разбор как во фронтенде, затем импорт через API (см. data/samples/README.md)."""

from pathlib import Path

import pytest
from front_csv import parse_csv

pytestmark = pytest.mark.e2e

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"


def _import(client, headers: dict, name: str) -> tuple[dict, list]:
    rows, errors = parse_csv((SAMPLES / name).read_text(encoding="utf-8"))
    response = client.post("/api/transactions/import", headers=headers, json={"rows": rows})
    assert response.status_code == 200, response.text
    return response.json(), errors


def test_ok_sample_imports_fully(client, new_user):
    result, errors = _import(client, new_user, "transactions_ok.csv")

    assert errors == []
    assert result == {"imported": 28, "rejected": [], "warnings": []}
    ops = client.get("/api/transactions", headers=new_user).json()
    assert {op["merchant"] for op in ops if op["isRecurring"]} == {
        "Аренда комнаты",
        "Музыкальная подписка",
        "Онлайн-кинотеатр",
        "Мобильная связь",
        "Проездной",
    }
    assert any(op["amount"] == -1250.5 for op in ops), "сумма «-1 250,50» в кавычках"


def test_errors_sample_rejects_by_row(client, new_user, demo_date):
    result, errors = _import(client, new_user, "transactions_errors.csv")

    assert [row for row, _ in errors] == [3, 4, 5, 6, 12]
    assert result["imported"] == 3
    messages = [r["message"] for r in result["rejected"]]
    assert len(messages) == 2
    assert "будущем" in messages[0] and "номер карты" in messages[1]
    assert len(result["warnings"]) == 1 and "уже есть" in result["warnings"][0]
    merchants = {op["merchant"] for op in client.get("/api/transactions", headers=new_user).json()}
    assert not any("2200" in m for m in merchants)
