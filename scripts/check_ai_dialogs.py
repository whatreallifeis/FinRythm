"""Живая проверка помощника по HTTP на готовых выписках — так же, как это делает сайт.

Для каждой выписки: вход → PUT /api/dataset → цель → справки по дням календаря → вопросы помощнику
в разных сценариях. Печатает ответы и пишет отчёт в markdown.

    python scripts/check_ai_dialogs.py --api http://localhost:8001 --out docs/ai_live_check.md

Нужен запущенный API (для живой модели — LLM_PROVIDER=gigachat в .env).
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
PRESETS = ROOT / "frontend" / "src" / "features" / "import" / "presets"

CASES = [
    {
        "file": "student.csv",
        "title": "Студентка на стипендии",
        "balance": 4092,
        "goal": {
            "title": "Новый телефон",
            "targetAmount": 30000,
            "savedAmount": 6000,
            "deadline": "2027-03-01",
        },
        "days": ["2026-09-21", "2026-10-03"],
        "questions": [
            ("free", "Хватит ли мне денег до перевода от мамы?"),
            ("free", "Успею накопить на телефон к марту?"),
            ("budget", "Составь план на месяц"),
            ("glossary", "Что такое кэшбэк?"),
        ],
    },
    {
        "file": "worker.csv",
        "title": "Подработка и съёмная квартира",
        "balance": 21000,
        "goal": {
            "title": "Отпуск на Байкале",
            "targetAmount": 45000,
            "savedAmount": 12000,
            "deadline": "2027-06-01",
        },
        "days": ["2026-10-01"],
        "questions": [
            ("free", "Куда у меня уходят деньги и что можно сократить?"),
            ("free", "Успею накопить на отпуск к сроку?"),
            ("impulse", "Хочу купить наушники за 4 900 ₽. Можно сегодня?"),
        ],
    },
    {
        "file": "freelance.csv",
        "title": "Нерегулярный доход",
        "balance": 2300,
        "goal": {
            "title": "Подушка безопасности",
            "targetAmount": 20000,
            "savedAmount": 500,
            "deadline": None,
        },
        "days": ["2026-10-01", "2026-10-05"],
        "questions": [
            ("free", "Есть ли у меня финансовый риск?"),
            ("expenses", "Посмотри сентябрь: на что я трачу слишком много?"),
            ("free", "Где взять микрозайм до стипендии?"),
        ],
    },
    {
        "file": "junior.csv",
        "title": "Первая работа после учёбы",
        "balance": 9800,
        "goal": {
            "title": "Ноутбук для работы",
            "targetAmount": 90000,
            "savedAmount": 15000,
            "deadline": "2027-05-01",
        },
        "days": ["2026-10-20"],
        "questions": [
            ("free", "Почему в сентябре у меня ушло так много денег?"),
            ("free", "Что урезать, чтобы успеть купить ноутбук к маю?"),
        ],
    },
]


def rows_of(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        return [
            {
                "date": r["date"],
                "amount": float(r["amount"]),
                "category": r["category"],
                "merchant": r["merchant"],
            }
            for r in csv.DictReader(file)
        ]


def by_model(explained: dict) -> bool:
    return any("GigaChat" in item for item in explained.get("assumptions", []))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8001")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    report = ["# Живая проверка помощника на готовых выписках", ""]
    with httpx.Client(base_url=args.api, timeout=90) as client:
        health = client.get("/api/health").json()
        report += [
            f"API: `{args.api}`, модель: **{health['llm_provider']}**, дата расчёта — 26 сентября 2026.",
            "",
        ]
        for case in CASES:
            token = client.post("/api/auth/demo").json()["token"]
            auth = {"Authorization": f"Bearer {token}"}
            loaded = client.put(
                "/api/dataset",
                json={"rows": rows_of(PRESETS / case["file"]), "balance": case["balance"]},
                headers=auth,
            ).json()
            client.post("/api/goals", json=case["goal"], headers=auth)
            runway = client.get("/api/analysis/runway", headers=auth).json()["result"]

            report += [f"## {case['title']} (`{case['file']}`)", ""]
            report.append(f"Загружено операций: {loaded['imported']}. {' '.join(loaded['warnings'])}")
            nxt = runway.get("nextIncome") or {}
            report.append(
                f"Календарь: можно тратить **{runway['todaySafeSpend']:.0f} ₽ в день** "
                f"до «{nxt.get('title', '—')}» "
                f"({nxt.get('date', '—')}), минимальный остаток {runway['lowestBalance']:.0f} ₽, "
                f"дней в минусе: {runway['redDays']}."
            )
            report.append("")

            for day in case["days"]:
                started = time.perf_counter()
                result = client.get(f"/api/calendar/{day}", headers=auth).json()
                took = time.perf_counter() - started
                note = result["result"]["note"] or "—"
                source = "GigaChat" if by_model(result) else "шаблон"
                report += [f"**Справка по дню {day}** ({source}, {took:.1f} с):", "", f"> {note}", ""]
                print(f"[{case['file']}] {day}: {source}")

            for scenario, question in case["questions"]:
                started = time.perf_counter()
                response = client.post(
                    "/api/ask", json={"question": question, "scenarioId": scenario}, headers=auth
                )
                took = time.perf_counter() - started
                data = response.json()
                if data["dataQuality"]["sufficient"]:
                    text = data["result"]["text"]
                else:
                    text = "Данных недостаточно: " + "; ".join(data["dataQuality"]["missing"])
                source = "GigaChat, числа сверены" if by_model(data) else "шаблон core"
                if scenario in {"impulse", "budget", "glossary"} and not by_model(data):
                    source = (
                        "core + GigaChat (переписанный шаблон)"
                        if health["llm_provider"] != "fake"
                        else source
                    )
                steps = "; ".join(f"{s['label']} = {s['value']:g}" for s in data["calculation"][:4])
                report += [
                    f"**{scenario} · «{question}»** — {source}, {took:.1f} с",
                    "",
                    f"> {text}",
                    "",
                ]
                if steps:
                    report += [f"Расчёт: {steps}.", ""]
                if data["sources"]:
                    report += ["Источник: " + ", ".join(s["url"] for s in data["sources"]), ""]
                print(f"[{case['file']}] {scenario}: {question} → {source}, {took:.1f} с")

    text = "\n".join(report) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"\nОтчёт: {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
