"""
ЭТАЛОННАЯ реализация формулы дневного лимита.

Назначение: спецификация в виде кода и генератор contracts/expected_results.json.
НЕ импортировать в прод-код. Боевая реализация — backend/app/core/runway.py (Саша),
она обязана давать те же числа (тест tests/core/test_expected_results.py).

Запуск:  python contracts/reference_runway.py  → печатает и перезаписывает expected_results.json
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).parent
CENT = D("0.01")


def _d(x) -> D:
    return D(str(x))


def _occurrences(p: dict, start: date, end: date) -> list[tuple[str, D, date]]:
    """Все платежи с датой в полуинтервале [start, end)."""
    out = []
    step = {"monthly": None, "weekly": 7, "once": 0}[p.get("period", "monthly")]
    dt = date.fromisoformat(p["next_date"])
    while dt < end:
        if dt >= start:
            out.append((p["title"], _d(p["amount"]), dt))
        if step == 0:
            break
        if step is None:  # +1 месяц, тот же день (упрощение: день ≤ 28 в демо-данных)
            m = dt.month + 1
            dt = dt.replace(year=dt.year + (m - 1) // 12, month=(m - 1) % 12 + 1)
        else:
            dt += timedelta(days=step)
    return out


def runway(profile: dict, purchase: D = D(0), delay_days: int = 0, k: D | None = None) -> dict:
    as_of = date.fromisoformat(profile["as_of"])
    s = profile.get("settings", {})
    reserve_pct = _d(s.get("reserve_pct", "10"))
    k = _d(s.get("expected_income_k", "0")) if k is None else k
    if profile.get("balance") is None:
        return {"status": "insufficient_data", "daily_limit": "0"}

    confirmed = sorted(
        (i for i in profile["incomes"] if i["confirmed"] and date.fromisoformat(i["date"]) >= as_of),
        key=lambda i: i["date"],
    )
    assumed = False
    if confirmed:
        nxt = date.fromisoformat(confirmed[0]["date"]) + timedelta(days=delay_days)
        horizon = max(1, (nxt - as_of).days)
    else:
        horizon = int(s.get("default_horizon_days", 30)) + delay_days
        nxt = as_of + timedelta(days=horizon)
        assumed = True
    end = as_of + timedelta(days=horizon)

    mandatory = sum((a for p in profile["payments"] for _, a, _ in _occurrences(p, as_of, end)), D(0))
    balance = _d(profile["balance"]) - purchase
    free = balance - mandatory
    reserve = (max(D(0), free) * reserve_pct / 100).quantize(CENT, ROUND_HALF_UP)
    per_day = sum((_d(g.get("daily_contribution", 0)) for g in profile.get("goals", [])), D(0))
    goal = min(per_day * horizon, max(D(0), free - reserve))
    expected = sum(
        (
            _d(i["amount"])
            for i in profile["incomes"]
            if not i["confirmed"] and as_of <= date.fromisoformat(i["date"]) < end
        ),
        D(0),
    )
    counted = (k * expected).quantize(CENT, ROUND_HALF_UP)
    available = free - reserve - goal + counted
    if available < 0:
        limit, deficit, status = D(0), -available, "deficit"
    else:
        limit, deficit, status = (available / horizon).quantize(D(1), ROUND_FLOOR), D(0), "ok"
    q = lambda x: str(_d(x).quantize(CENT))  # noqa: E731
    return {
        "status": status,
        "horizon_days": horizon,
        "horizon_is_assumed": assumed,
        "next_income_date": nxt.isoformat(),
        "mandatory_total": q(mandatory),
        "free": q(free),
        "reserve": q(reserve),
        "goal_contribution": q(goal),
        "expected_income_counted": q(counted),
        "available": q(available),
        "daily_limit": str(limit),
        "deficit": q(deficit),
    }


def goal_plan(target: D, saved: D, deadline: date, as_of: date, current_daily: D) -> dict:
    days_left = (deadline - as_of).days
    need = target - saved
    required = (need / days_left).quantize(D(1), ROUND_CEILING) if days_left > 0 else need
    by_deadline = saved + current_daily * max(0, days_left)
    projected = None
    if current_daily > 0:
        days_needed = int((need / current_daily).to_integral_value(ROUND_CEILING))
        projected = (as_of + timedelta(days=days_needed)).isoformat()
    return {
        "days_left": days_left,
        "required_daily": str(required),
        "amount_by_deadline": str(by_deadline.quantize(CENT)),
        "projected_date": projected,
        "on_track": by_deadline >= target,
    }


def load(name: str) -> dict:
    return json.loads((HERE / "profiles" / f"{name}.json").read_text(encoding="utf-8"))


def build() -> dict:
    p1, p2, p3 = load("p1"), load("p2"), load("p3")
    return {
        "_comment": "Сгенерировано contracts/reference_runway.py. Ручная правка запрещена.",
        "runway": {
            "p1": runway(p1),
            "p1_purchase_3000": runway(p1, purchase=D(3000)),
            "p1_delay_7": runway(p1, delay_days=7),
            "p1_k_0_5": runway(p1, k=D("0.5")),
            "p2": runway(p2),
            "p3": runway(p3),
            "p3_k_0_5": runway(p3, k=D("0.5")),
            "edge_income_today": runway(load("edge_income_today")),
            "edge_empty": runway(load("edge_empty")),
        },
        "goal_plan": {
            "p1_laptop": goal_plan(D(60000), D(0), date(2027, 3, 31), date(2026, 9, 26), D(100)),
        },
    }


if __name__ == "__main__":
    res = build()
    text = json.dumps(res, ensure_ascii=False, indent=2)
    (HERE / "expected_results.json").write_text(text + "\n", encoding="utf-8")
    print(text)
