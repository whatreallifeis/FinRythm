"""Отказ на запросы, которые продукт не имеет права закрывать советом."""

import re

EDUCATION_SOURCE = {
    "title": "Финансовая культура — Банк России",
    "url": "https://fincult.info/",
}

_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"крипт|биткоин|bitcoin|эфир|nft", re.I), "криптовалюты"),
    (re.compile(r"куда вложить|инвестир|акци[ий]|облигац|портфел", re.I), "инвестиций"),
    (re.compile(r"оформи(ть)? кредит|взять кредит|займ|микрозайм|в кредит", re.I), "кредита"),
    (re.compile(r"казино|ставк[аи] на спорт|букмекер", re.I), "азартных ставок"),
    (re.compile(r"реши за меня|скажи,? что делать с деньгами|переведи деньги", re.I), "решения за вас"),
    (re.compile(r"\bcvv\b|парол|полный номер карт|пин-код|sms-код", re.I), "секретных данных"),
]


def refusal(question: str) -> str | None:
    for pattern, topic in _RULES:
        if pattern.search(question):
            return topic
    return None
