import json
from pathlib import Path

import pytest
from app.models import Profile

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"


def load_profile(name: str) -> Profile:
    return Profile.model_validate_json((CONTRACTS / "profiles" / f"{name}.json").read_text(encoding="utf-8"))


def load_expected() -> dict:
    return json.loads((CONTRACTS / "expected_results.json").read_text(encoding="utf-8"))


@pytest.fixture
def p1() -> Profile:
    return load_profile("p1")


@pytest.fixture
def p2() -> Profile:
    return load_profile("p2")


@pytest.fixture
def p3() -> Profile:
    return load_profile("p3")
