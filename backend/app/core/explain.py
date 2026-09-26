from decimal import Decimal


def step(label: str, formula: str, value: Decimal | int) -> dict:
    number = float(value) if isinstance(value, int) else float(value)
    return {"label": label, "formula": formula, "value": number}


def explained(
    result: dict,
    *,
    assumptions: list[str],
    calculation: list[dict],
    limitations: list[str],
    sufficient: bool,
    missing: list[str],
    coverage_days: int,
    sources: list[dict] | None = None,
) -> dict:
    return {
        "result": result,
        "assumptions": assumptions,
        "calculation": calculation,
        "sources": sources or [],
        "limitations": limitations,
        "dataQuality": {
            "sufficient": sufficient,
            "missing": missing,
            "coverageDays": coverage_days,
        },
    }


COMMON_LIMITS = [
    "Расчёт сделан по загруженным данным. Банковские счета не подключены.",
    "Это не инвестиционная рекомендация и не операция с деньгами. Решение остаётся за вами.",
]
