"""База знаний и поиск BM25 (A6). Формат фрагментов — contracts/data_formats.md §3.

Токенизация по ТЗ: нижний регистр, ё→е, слова короче 3 букв и служебные слова вопроса отбрасываются,
грубый стемминг: обрезка до 7 символов и снятие конечных гласных («ставка»/«ставку» → «ставк»;
6 символов мало: «самозанятый» и «самозапрет» совпали бы). В вопросе «что такое X? …» ищем по X.
К баллу BM25 добавляется бонус за совпадение с заголовком: «инфляция» находит «Инфляцию», а не
фрагмент, где слово просто часто встречается. Ниже порога — пусто: помощник не придумывает ответ.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

log = logging.getLogger(__name__)

STEM = 7
VOWELS = "аеиоуыэюяйь"
# Минимальный балл: ниже — считаем, что проверенного ответа в базе нет.
MIN_SCORE = 1.0
# Сколько добавить, если запрос покрывает весь заголовок фрагмента (частичное покрытие — пропорционально).
TITLE_BONUS = 3.0

STOP_WORDS = {
    "что",
    "такое",
    "так",
    "такой",
    "такая",
    "такие",
    "кто",
    "это",
    "как",
    "где",
    "когда",
    "зачем",
    "почему",
    "какой",
    "какая",
    "какое",
    "какие",
    "объясни",
    "объясните",
    "расскажи",
    "расскажите",
    "значит",
    "означает",
    "простыми",
    "словами",
    "простым",
    "языком",
    "мне",
    "меня",
    "мой",
    "моих",
    "моей",
    "для",
    "про",
    "или",
    "при",
    "работает",
    "пример",
    "примером",
    "увидел",
    "увидела",
    "встретил",
    "встретила",
    "новостях",
}

REQUIRED = ("id", "title", "text", "keywords", "url", "checked_at")


def stem(word: str) -> str:
    word = word[:STEM]
    while len(word) > 3 and word[-1] in VOWELS:
        word = word[:-1]
    return word


# «Что такое инфляция? Увидела в новостях про ставку» — термин здесь «инфляция», остальное контекст.
_TERM = re.compile(
    r"(?:что такое|что значит|что означает|кто такой|кто такие|объясни(?:те)?,?(?: что такое)?)"
    r"\s+([^?.!,;]+)",
    re.IGNORECASE,
)


def focus(query: str) -> str:
    """Термин из вопроса-определения или весь вопрос."""
    match = _TERM.search(query.replace("ё", "е"))
    return match.group(1) if match and tokenize(match.group(1)) else query


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zа-я0-9]+", text.casefold().replace("ё", "е"))
    return [stem(w) for w in words if len(w) >= 3 and w not in STOP_WORDS]


class KnowledgeBase:
    def __init__(self, fragments: list[dict[str, Any]]):
        self.fragments = fragments
        docs = [self._doc_tokens(f) for f in fragments]
        self._titles = [set(tokenize(f["title"])) for f in fragments]
        # Заголовок и ключевые слова: о чём фрагмент (для вопросов-определений).
        self._heads = [set(tokenize(" ".join([f["title"], *f.get("keywords", [])]))) for f in fragments]
        self._bm25 = BM25Okapi(docs) if docs else None

    @staticmethod
    def _doc_tokens(fragment: dict) -> list[str]:
        # Заголовок и ключевые слова важнее текста — повторяем их, чтобы поднять вес.
        head = " ".join([fragment["title"], *fragment.get("keywords", [])])
        return tokenize(head) * 3 + tokenize(fragment["text"])

    def __len__(self) -> int:
        return len(self.fragments)

    def search(self, query: str, k: int = 3, min_score: float = MIN_SCORE) -> list[dict[str, Any]]:
        """До k фрагментов, лучший первым; пусто, если ничего не набрало min_score.

        В вопросе-определении («что такое дюрация облигации») первые слова термина должны быть
        в заголовке или ключевых словах фрагмента: иначе мы ответили бы про облигации, а не про дюрацию.
        """
        term = focus(query)
        tokens = tokenize(term)
        if self._bm25 is None or not tokens:
            return []
        head_terms = set(tokens[:2]) if term != query else set()
        query = set(tokens)
        scores = [
            score + (TITLE_BONUS * len(title & query) / len(title) if title else 0.0)
            for score, title in zip(self._bm25.get_scores(tokens), self._titles, strict=True)
        ]
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [self.fragments[i] for i in ranked if scores[i] >= min_score and head_terms <= self._heads[i]][
            :k
        ]


def load_kb(path: str | Path) -> KnowledgeBase:
    """База из JSON-файла. Нет файла или он битый — пустая база, приложение не падает."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        log.warning("База знаний %s не найдена — справочник отвечает «нет проверенного источника»", path)
        return KnowledgeBase([])
    except (OSError, json.JSONDecodeError) as exc:
        log.error("База знаний %s не читается: %s", path, exc)
        return KnowledgeBase([])
    fragments = [f for f in data if isinstance(f, dict) and all(f.get(key) for key in REQUIRED)]
    if len(fragments) != len(data):
        log.warning(
            "В базе знаний пропущено фрагментов без обязательных полей: %d", len(data) - len(fragments)
        )
    return KnowledgeBase(fragments)
