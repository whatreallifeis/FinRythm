"""Контракт публичного интерфейса core/ingest: каждая функция на P1 возвращает объект нужного типа."""

import datetime as dt
from decimal import Decimal

from app.core import (
    build_snapshot,
    calculate_runway,
    categorize,
    detect_recurring,
    detect_risks,
    plan_all_goals,
    plan_goal,
    simulate,
    spending_breakdown,
)
from app.ingest import import_csv
from app.models import (
    Breakdown,
    GoalPlan,
    ImportReport,
    Profile,
    RecurringItem,
    RiskReport,
    RunwayResult,
    SimulationResult,
)


def test_calculate_runway(p1):
    assert isinstance(calculate_runway(p1), RunwayResult)


def test_simulate(p1):
    res = simulate(p1, purchase=Decimal(3000))
    assert isinstance(res, SimulationResult)
    assert res.delta_daily_limit == res.after.daily_limit - res.before.daily_limit


def test_plan_goal(p1):
    plan = plan_goal(p1, target_amount=Decimal(60000), deadline=dt.date(2027, 3, 31))
    assert isinstance(plan, GoalPlan)


def test_plan_all_goals(p1):
    plans = plan_all_goals(p1)
    assert len(plans) == len(p1.goals)
    assert all(isinstance(p, GoalPlan) for p in plans)


def test_build_snapshot(p1):
    snap = build_snapshot(p1)
    assert isinstance(snap, dict)
    assert snap["as_of"] == "2026-09-26"


def test_categorize():
    assert isinstance(categorize("Пятёрочка", Decimal("-350")), str)


def test_detect_recurring(p1):
    items = detect_recurring(p1.transactions)
    assert isinstance(items, list)
    assert all(isinstance(i, RecurringItem) for i in items)


def test_spending_breakdown(p1):
    res = spending_breakdown(p1)
    assert res is None or isinstance(res, Breakdown)


def test_detect_risks(p1):
    assert isinstance(detect_risks(p1), RiskReport)


def test_import_csv(p1):
    profile, report = import_csv(p1, b"date,amount,description\n", mode="append")
    assert isinstance(profile, Profile)
    assert isinstance(report, ImportReport)
    assert report.mode == "append"
