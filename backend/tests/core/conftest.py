import pytest
from app.models import Profile
from core_helpers import load_profile


@pytest.fixture
def p1() -> Profile:
    return load_profile("p1")


@pytest.fixture
def p2() -> Profile:
    return load_profile("p2")


@pytest.fixture
def p3() -> Profile:
    return load_profile("p3")
