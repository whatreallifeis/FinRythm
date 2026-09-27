"""CSV-выписка → все посчитанные числа: доходы, расходы, категории, регулярные платежи, остатки, цели, риски.

Считает тот же код, что отвечает сайту и помощнику (app.core.build_report), без сервера и без модели.

    python scripts/csv_report.py frontend/src/features/import/presets/student.csv --balance 4092
    python scripts/csv_report.py выписка.csv --balance 18430 --as-of 2026-09-26 --json > сводка.json
    python scripts/csv_report.py выписка.csv --balance 4092 --goal "Телефон;30000;6000;2027-03-01"

Формат CSV — как на вкладке «Данные»: date,amount,category,merchant (расход со знаком минус).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.serialize import to_json  # noqa: E402
from app.core import build_report, report_text  # noqa: E402
from app.ingest import state_from_csv  # noqa: E402
from app.models import SavingGoal  # noqa: E402


def parse_goal(text: str, index: int) -> SavingGoal:
    """«Название;сумма;накоплено;срок» — срок можно не указывать."""
    parts = [part.strip() for part in text.split(";")]
    if len(parts) < 2:
        raise argparse.ArgumentTypeError("цель: «Название;сумма[;накоплено[;ГГГГ-ММ-ДД]]»")
    return SavingGoal(
        id=f"g-{index}",
        title=parts[0],
        target_amount=Decimal(parts[1]),
        saved_amount=Decimal(parts[2]) if len(parts) > 2 and parts[2] else Decimal(0),
        deadline=dt.date.fromisoformat(parts[3]) if len(parts) > 3 and parts[3] else None,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("csv", type=Path, help="файл выписки CSV")
    parser.add_argument("--balance", type=Decimal, help="текущий баланс, ₽ (в строках выписки его нет)")
    parser.add_argument(
        "--as-of", type=dt.date.fromisoformat, default=dt.date(2026, 9, 26), help="дата расчёта"
    )
    parser.add_argument("--goal", action="append", default=[], help="цель «Название;сумма;накоплено;срок»")
    parser.add_argument("--json", action="store_true", help="вывести сводку в JSON")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    state, result = state_from_csv(args.csv.read_text(encoding="utf-8"), args.balance, args.as_of)
    state = state.model_copy(update={"goals": [parse_goal(g, i) for i, g in enumerate(args.goal, 1)]})
    report = build_report(state, args.as_of)

    if args.json:
        print(
            json.dumps({"import": to_json(result), "report": to_json(report)}, ensure_ascii=False, indent=2)
        )
        return 0
    print(f"Загружено операций: {result.imported}, отклонено: {len(result.rejected)}")
    for row in result.rejected:
        print(f"  строка {row.row}: {row.message}")
    for warning in result.warnings:
        print(f"  {warning}")
    print()
    print(report_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
