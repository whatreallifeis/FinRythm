"""Точка входа помощника для POST /api/ask (сценарии ruina696, origin/front:docs/ai-scenarios.md).

API передаёт вопрос, scenarioId и данные пользователя, получает Explained с result = {"text": ...}.
Числа в ответе считает только app.core; здесь — выбор сценария и текст вокруг готовых чисел.
"""

from __future__ import annotations

import datetime as dt

from app.ai.llm.base import LLMClient
from app.ai.tools import KnowledgeSearch
from app.models import SCENARIO_IDS, DataQuality, Explained, ScenarioId, UserState

COMMON_LIMITS = [
    "Расчёт сделан по загруженным данным. Банковские счета не подключены.",
    "Это не инвестиционная рекомендация и не операция с деньгами. Решение остаётся за вами.",
]


async def ask(
    question: str,
    scenario_id: ScenarioId,
    state: UserState,
    as_of: dt.date,
    *,
    llm: LLMClient | None = None,
    kb: KnowledgeSearch | None = None,
) -> Explained:
    """Ответ помощника на вопрос пользователя в сценарии scenario_id.

    Заглушка AF1: сигнатура и форма ответа окончательные, сценарии появятся в AF2.
    """
    if scenario_id not in SCENARIO_IDS:
        raise ValueError(f"Неизвестный сценарий {scenario_id!r}. Доступны: {', '.join(SCENARIO_IDS)}.")
    return Explained(
        result={"text": ""},
        limitations=COMMON_LIMITS,
        data_quality=DataQuality(
            sufficient=False,
            missing=["помощник ещё настраивается — попробуйте задать вопрос чуть позже"],
        ),
    )
