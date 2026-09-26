"""Проверки настоящей базы знаний data/knowledge_base/kb.json (формат — contracts/data_formats.md §3)."""

import datetime as dt
import json
from pathlib import Path

import pytest
from app.ai import ask
from app.ai.guardrails import KB_QUERIES
from app.ai.rag import load_kb
from app.core import DEMO_AS_OF, load_demo_state

KB_PATH = Path(__file__).resolve().parents[3] / "data" / "knowledge_base" / "kb.json"
RAW = json.loads(KB_PATH.read_text(encoding="utf-8"))
KB = load_kb(KB_PATH)
ALLOWED_DOMAINS = (
    "https://fincult.info/",
    "https://www.cbr.ru/",
    "https://cbr.ru/",
    "https://minobrnauki.gov.ru/",
)


def test_size_and_fields():
    assert 40 <= len(RAW) <= 60
    assert len(KB) == len(RAW)  # ни один фрагмент не отброшен загрузчиком
    assert len({f["id"] for f in RAW}) == len(RAW)
    for f in RAW:
        assert set(f) <= {"id", "title", "text", "keywords", "source_title", "url", "checked_at", "mistake"}
        assert f["url"].startswith(ALLOWED_DOMAINS), f["id"]
        assert 80 <= len(f["text"].split()) <= 250, f["id"]
        assert f["keywords"], f["id"]
        dt.date.fromisoformat(f["checked_at"])


def top(query: str) -> str:
    found = KB.search(query, k=1)
    assert found, f"ничего не найдено: {query}"
    return found[0]["id"]


@pytest.mark.parametrize(
    ("query", "kb_id"),
    [
        ("Что такое подушка безопасности?", "kb-001"),
        ("Что такое инфляция? Увидела в новостях про ставку", "kb-002"),
        ("что такое личная инфляция", "kb-003"),
        ("Что значит ключевая ставка?", "kb-004"),
        ("что такое вклад", "kb-005"),
        ("Объясни сложный процент", "kb-006"),
        ("что такое капитализация", "kb-006"),
        ("накопительный счёт", "kb-007"),
        ("как работает страхование вкладов", "kb-008"),
        ("что такое ПСК", "kb-011"),
        ("что такое кредитная история", "kb-013"),
        ("Что такое кредитная история и как её проверить?", "kb-013"),
        ("Что такое налог на вклады?", "kb-009"),
        ("что такое кредитный рейтинг", "kb-015"),
        ("что такое самозапрет на кредиты", "kb-016"),
        ("что такое льготный период по кредитной карте", "kb-017"),
        ("что такое оплата частями", "kb-018"),
        ("что такое кешбэк", "kb-025"),
        ("что такое чарджбэк", "kb-026"),
        ("что такое СБП", "kb-027"),
        ("что такое финансовая пирамида", "kb-033"),
        ("что такое облигация", "kb-037"),
        ("что такое ПИФ", "kb-039"),
        ("кто такой самозанятый", "kb-040"),
        ("что такое налоговый вычет за обучение", "kb-042"),
        ("какие бывают стипендии", "kb-043"),
    ],
)
def test_glossary_terms_found(query, kb_id):
    assert top(query) == kb_id


@pytest.mark.parametrize(
    ("intent", "kb_id"),
    [
        ("investment", "kb-036"),
        ("crypto", "kb-034"),
        ("credit", "kb-010"),
        ("gambling", "kb-035"),
        ("personal_data", "kb-029"),
    ],
)
def test_refusal_topics_have_source(intent, kb_id):
    assert top(KB_QUERIES[intent]) == kb_id


@pytest.mark.parametrize(
    "query",
    [
        "что такое дюрация",
        "Что такое дюрация облигации?",
        "что такое мультипликатор P/E",
        "расскажи анекдот",
        "как приготовить борщ",
    ],
)
def test_unknown_is_empty(query):
    assert KB.search(query) == []


async def test_glossary_scenario_with_real_kb():
    res = await ask("Что такое инфляция?", "glossary", load_demo_state(), DEMO_AS_OF, kb=KB)
    assert res.data_quality.sufficient
    assert res.result["text"].startswith("Инфляция — это устойчивый рост")
    assert "Типичная ошибка:" in res.result["text"]
    assert res.sources[0].url == "https://fincult.info/article/chto-takoe-inflyatsiya-i-otkuda-ona-beretsya/"


async def test_credit_refusal_cites_kb():
    res = await ask("Взять микрозайм до стипендии?", "free", load_demo_state(), DEMO_AS_OF, kb=KB)
    assert res.sources[0].url == "https://fincult.info/article/mikrozaem/"
