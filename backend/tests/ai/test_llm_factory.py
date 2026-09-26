from types import SimpleNamespace

import pytest
from app.ai import get_llm
from app.ai.llm.fake import FakeLLM


def test_fake_provider():
    llm = get_llm(SimpleNamespace(llm_provider="fake"))
    assert isinstance(llm, FakeLLM)
    assert llm.name == "fake"


def test_provider_name_is_case_insensitive():
    assert isinstance(get_llm(SimpleNamespace(llm_provider=" FAKE ")), FakeLLM)


def test_unknown_provider_fails_with_clear_message():
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        get_llm(SimpleNamespace(llm_provider="skynet"))
