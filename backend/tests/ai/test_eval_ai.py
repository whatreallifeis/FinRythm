"""Оценка качества (scripts/eval_ai.py) не должна деградировать: все 30 вопросов проходят."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_eval_ai_all_cases_pass():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "eval_ai.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Пройдено 30 из 30" in result.stdout
