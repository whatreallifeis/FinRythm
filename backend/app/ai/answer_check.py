"""Проверка ответа модели сверх чисел (issue #65): язык и смысл.

Проверка чисел (number_check) не видит, что модель:
- смешала языки — «Ваше money уходит mostly на развлечения», иероглифы посреди фразы;
- поменяла смысл при тех же числах — «сможете накопить 12 657 ₽» вместо «откладывайте 12 657 ₽ в месяц»;
- начала с «Да», хотя вердикт — «не влезает».
Поэтому вердикт (первая фраза черновика) остаётся дословно, а продолжение модели проверяется здесь.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

# Иероглифы, хангыль, кана, арабская письменность и др. — в русском ответе их быть не может.
_FOREIGN_SCRIPT = re.compile(r"[\u0600-\u06ff\u3000-\u9fff\uac00-\ud7af\uf900-\ufaff\uff00-\uffef]")
_LATIN_WORD = re.compile(r"\b[a-zA-Z]{2,}\b")
# Латинские сокращения, которые нормально звучат в русском финансовом тексте.
LATIN_ALLOWED = {"cvc", "cvv", "pin", "sms", "bnpl", "etf", "qr", "id", "csv"}
_PERIOD = r"(в день|в месяц|в год|в неделю)"
_AMOUNT_WITH_PERIOD = re.compile(rf"(\d[\d \u00a0]*(?:[.,]\d+)?)\s*₽?\s*{_PERIOD}")
_YES_NO = re.compile(r"^\s*«?(да|нет)\b", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[«\"(]?[А-ЯЁA-Z0-9])")


def split_verdict(draft: str) -> tuple[str, str]:
    """(первая фраза черновика, остальное). Первая фраза — вердикт, его модель не переписывает."""
    parts = _SENTENCE_END.split(draft.strip(), maxsplit=1)
    return (parts[0], parts[1] if len(parts) > 1 else "")


def _words(texts: Iterable[Any]) -> set[str]:
    out: set[str] = set()
    for text in texts:
        if isinstance(text, str):
            out.update(w.lower() for w in _LATIN_WORD.findall(text))
        elif isinstance(text, dict):
            out |= _words(text.values())
        elif isinstance(text, list | tuple):
            out |= _words(text)
    return out


def language_problem(text: str, sources: Iterable[Any] = ()) -> str | None:
    """Почему текст не чисто русский, или None. Латиница из вопроса и источников разрешена."""
    if _FOREIGN_SCRIPT.search(text):
        return "в ответе есть иероглифы или другие нерусские буквы"
    allowed = LATIN_ALLOWED | _words(sources)
    foreign = sorted({w for w in (m.lower() for m in _LATIN_WORD.findall(text)) if w not in allowed})
    if foreign:
        return "в ответе английские слова: " + ", ".join(foreign)
    return None


def _norm(number: str) -> str:
    return re.sub(r"[ \u00a0]", "", number).replace(",", ".")


def meaning_problem(text: str, draft: str) -> str | None:
    """Почему продолжение модели меняет смысл черновика, или None."""
    if _YES_NO.match(text) and not _YES_NO.match(draft):
        return "не начинай с «да» или «нет» — вердикт уже написан"
    periods = {_norm(m.group(1)): m.group(2) for m in _AMOUNT_WITH_PERIOD.finditer(draft)}
    for number, period in periods.items():
        for match in re.finditer(r"\d[\d \u00a0]*(?:[.,]\d+)?", text):
            if _norm(match.group()) != number:
                continue
            tail = text[match.end() : match.end() + 25]
            if period not in tail:
                return f"сумма {match.group().strip()} ₽ в черновике указана «{period}» — сохрани это"
    return None
