import json

from app.ai.rag import KnowledgeBase, load_kb, tokenize


def frag(i: int, title: str, keywords: list[str], text: str) -> dict:
    return {
        "id": f"kb-{i:03}",
        "title": title,
        "text": text,
        "keywords": keywords,
        "source_title": "Банк России",
        "url": f"https://fincult.info/{i}/",
        "checked_at": "2026-09-26",
    }


FRAGMENTS = [
    frag(
        1,
        "Финансовая подушка безопасности",
        ["подушка", "резерв", "запас"],
        "Подушка безопасности — запас денег на обязательные расходы на случай, если доход пропадёт.",
    ),
    frag(
        2,
        "Инфляция",
        ["инфляция", "рост цен"],
        "Инфляция — устойчивый рост цен: на ту же сумму со временем можно купить меньше товаров.",
    ),
    frag(
        3,
        "Ключевая ставка",
        ["ключевая ставка", "Банк России"],
        "Ключевая ставка — процент, под который Банк России кредитует банки и принимает их депозиты.",
    ),
    frag(
        4,
        "Микрозаймы и их риски",
        ["микрозайм", "МФО", "ПСК"],
        "Микрозайм — небольшой кредит на короткий срок под очень высокий процент.",
    ),
    frag(
        5,
        "Кредитная история",
        ["кредитная история", "БКИ"],
        "Кредитная история — сведения о том, как человек брал и возвращал кредиты и займы.",
    ),
]
KB = KnowledgeBase(FRAGMENTS)


def test_tokenize_stems_and_drops_question_words():
    assert tokenize("Что такое подушка безопасности?") == ["подушк", "безопас"]
    assert tokenize("ставка ставку ставки") == ["ставк"] * 3
    assert tokenize("Ёжик и рост цен") == ["ежик", "рост", "цен"]


def test_focus_on_defined_term():
    assert KB.search("Что такое инфляция? Увидела в новостях про ставку")[0]["id"] == "kb-002"


def test_cushion_first():
    assert KB.search("что такое подушка безопасности")[0]["id"] == "kb-001"


def test_other_terms():
    assert KB.search("Объясни, что такое инфляция")[0]["id"] == "kb-002"
    assert KB.search("что значит ключевая ставка")[0]["id"] == "kb-003"
    assert KB.search("микрозаймы полная стоимость кредита")[0]["id"] == "kb-004"
    assert KB.search("Что такое кредитная история?")[0]["id"] == "kb-005"


def test_word_forms():
    assert KB.search("про подушку")[0]["id"] == "kb-001"
    assert KB.search("инфляции")[0]["id"] == "kb-002"


def test_unknown_term_is_empty():
    assert KB.search("что такое дюрация") == []
    assert KB.search("что такое") == []


def test_k_limits_results():
    assert len(KB.search("кредит ставка займы", k=2)) <= 2


def test_load_kb(tmp_path):
    path = tmp_path / "kb.json"
    broken = frag(9, "Без ссылки", ["x"], "текст") | {"url": ""}
    path.write_text(json.dumps([FRAGMENTS[0], broken], ensure_ascii=False), encoding="utf-8")
    kb = load_kb(path)
    assert len(kb) == 1


def test_load_kb_missing_or_broken(tmp_path):
    assert len(load_kb(tmp_path / "nope.json")) == 0
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert load_kb(bad).search("подушка") == []
