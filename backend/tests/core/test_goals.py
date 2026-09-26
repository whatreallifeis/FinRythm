import datetime as dt
from decimal import Decimal

from app.core import plan_all_goals, plan_goal
from core_helpers import load_expected

EXPECTED = load_expected()["goal_plan"]


def test_p1_laptop_matches_reference(p1):
    plan = plan_goal(
        p1,
        target_amount=Decimal(60000),
        deadline=dt.date(2027, 3, 31),
        saved_amount=Decimal(0),
        title="Ноутбук",
        goal_id="g1",
    ).model_dump(mode="json")
    for field, expected in EXPECTED["p1_laptop"].items():
        assert plan[field] == expected, field
    assert plan["current_daily"] == "100.00"


def test_unknown_goal_has_zero_pace(p1):
    plan = plan_goal(p1, target_amount=Decimal(10000), deadline=dt.date(2026, 12, 25))
    assert plan.current_daily == 0
    assert plan.projected_date is None
    assert plan.amount_by_deadline == Decimal("0.00")
    assert not plan.on_track
    assert plan.required_daily == Decimal(112)  # 10 000 / 90 = 111,1 → вверх до 112


def test_deadline_passed(p1):
    plan = plan_goal(
        p1, target_amount=Decimal(5000), deadline=dt.date(2026, 9, 1), saved_amount=Decimal("1200.50")
    )
    assert plan.days_left == -25
    assert plan.required_daily == Decimal(3800)
    assert not plan.on_track


def test_deadline_today(p1):
    plan = plan_goal(p1, target_amount=Decimal(500), deadline=dt.date(2026, 9, 26))
    assert plan.days_left == 0
    assert plan.required_daily == Decimal(500)
    assert not plan.on_track


def test_already_saved(p1):
    plan = plan_goal(
        p1,
        target_amount=Decimal(1000),
        deadline=dt.date(2026, 12, 1),
        saved_amount=Decimal(1500),
        goal_id="g1",
    )
    assert plan.required_daily == 0
    assert plan.on_track
    assert plan.projected_date == dt.date(2026, 9, 26)


def test_on_track_when_pace_enough(p1):
    plan = plan_goal(p1, target_amount=Decimal(3000), deadline=dt.date(2026, 12, 31), goal_id="g1")
    assert plan.on_track
    assert plan.projected_date == dt.date(2026, 9, 26) + dt.timedelta(days=30)


def test_plan_all_goals(p1, p3):
    plans = plan_all_goals(p1)
    assert [(p.goal_id, p.required_daily) for p in plans] == [("g1", Decimal(323))]
    assert plan_all_goals(p3) == []
