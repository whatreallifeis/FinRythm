"""Боевой calculate_runway совпадает с contracts/expected_results.json до копейки."""

from decimal import Decimal

import pytest
from app.core import calculate_runway
from core_helpers import load_expected, load_profile

CASES = {
    "p1": ("p1", {}),
    "p1_purchase_3000": ("p1", {"purchase": Decimal(3000)}),
    "p1_delay_7": ("p1", {"delay_days": 7}),
    "p1_k_0_5": ("p1", {"k": Decimal("0.5")}),
    "p2": ("p2", {}),
    "p3": ("p3", {}),
    "p3_k_0_5": ("p3", {"k": Decimal("0.5")}),
    "edge_income_today": ("edge_income_today", {}),
    "edge_empty": ("edge_empty", {}),
}

EXPECTED = load_expected()["runway"]


def test_all_expected_keys_covered():
    assert set(EXPECTED) == set(CASES)


@pytest.mark.parametrize("key", sorted(EXPECTED))
def test_runway_matches_reference(key):
    profile_name, kwargs = CASES[key]
    result = calculate_runway(load_profile(profile_name), **kwargs).model_dump(mode="json")
    for field, expected in EXPECTED[key].items():
        assert result[field] == expected, f"{key}.{field}"
