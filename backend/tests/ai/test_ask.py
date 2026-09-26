import datetime as dt

import pytest
from app.ai import FakeLLM, ask
from app.models import SCENARIO_IDS, Explained, UserState

AS_OF = dt.date(2026, 9, 26)


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
async def test_ask_returns_explained_for_every_scenario(scenario_id):
    res = await ask(
        "Хватит ли мне денег до стипендии?", scenario_id, UserState(), AS_OF, llm=FakeLLM(), kb=None
    )
    assert isinstance(res, Explained)
    assert set(res.result) == {"text"}
    if not res.data_quality.sufficient:
        assert res.data_quality.missing


async def test_ask_serializes_for_api():
    res = await ask("что такое инфляция", "glossary", UserState(), AS_OF, llm=FakeLLM(), kb=None)
    data = res.model_dump(mode="json")
    assert set(data) == {"result", "assumptions", "calculation", "sources", "limitations", "data_quality"}


async def test_ask_unknown_scenario():
    with pytest.raises(ValueError, match="Неизвестный сценарий"):
        await ask("вопрос", "chat", UserState(), AS_OF, llm=FakeLLM(), kb=None)
