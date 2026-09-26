"""Состояние пользователя в SQLite одним JSON-документом.

Деньги в файле — строки Decimal. В ответ API они превращаются в числа только на границе.
"""

import json
import sqlite3
from copy import deepcopy
from decimal import Decimal

from app.demo_data import DEMO_GOALS, DEMO_INCOMES, DEMO_TRANSACTIONS
from app.money import D


def connect(path: str) -> sqlite3.Connection:
    # Соединение создаётся в одном потоке FastAPI, а запрос читает его в другом.
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            mode TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS states (
            user_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL
        )
        """
    )
    return connection


def empty_state() -> dict:
    return {"balance": None, "incomes": [], "goals": [], "transactions": [], "history": []}


def demo_state() -> dict:
    return {
        "balance": "18430.00",
        "incomes": deepcopy(DEMO_INCOMES),
        "goals": deepcopy(DEMO_GOALS),
        "transactions": deepcopy(DEMO_TRANSACTIONS),
        "history": [],
    }


class Store:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._db = connection

    def create_session(self, token: str, user_id: str, display_name: str, mode: str) -> None:
        self._db.execute(
            "INSERT INTO sessions (token, user_id, display_name, mode) VALUES (?, ?, ?, ?)",
            (token, user_id, display_name, mode),
        )
        self._db.execute(
            """
            INSERT INTO states (user_id, payload) VALUES (?, ?)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (user_id, json.dumps(empty_state(), ensure_ascii=False)),
        )
        self._db.commit()

    def session(self, token: str) -> dict | None:
        row = self._db.execute("SELECT * FROM sessions WHERE token = ?", (token,)).fetchone()
        if row is None:
            return None
        return {
            "token": row["token"],
            "userId": row["user_id"],
            "displayName": row["display_name"],
            "mode": row["mode"],
        }

    def load(self, user_id: str) -> dict:
        row = self._db.execute("SELECT payload FROM states WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return empty_state()
        return json.loads(row["payload"])

    def save(self, user_id: str, state: dict) -> None:
        payload = json.dumps(state, ensure_ascii=False)
        self._db.execute(
            """
            INSERT INTO states (user_id, payload) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET payload = excluded.payload
            """,
            (user_id, payload),
        )
        self._db.commit()

    def seed(self, user_id: str) -> None:
        self.save(user_id, demo_state())

    def clear(self, user_id: str) -> None:
        self.save(user_id, empty_state())


def public_profile(state: dict) -> dict:
    return {
        "balance": float(D(state["balance"])) if state["balance"] is not None else 0,
        "incomes": [_public_income(item) for item in state["incomes"]],
        "goals": [_public_goal(item) for item in state["goals"]],
    }


def public_transactions(state: dict) -> list[dict]:
    rows = [_public_transaction(item) for item in state["transactions"]]
    rows.sort(key=lambda item: item["date"], reverse=True)
    return rows


def _public_income(item: dict) -> dict:
    return {
        "id": item["id"],
        "title": item["title"],
        "amount": float(D(item["amount"])),
        "dayOfMonth": int(item["dayOfMonth"]),
    }


def _public_goal(item: dict) -> dict:
    return {
        "id": item["id"],
        "title": item["title"],
        "targetAmount": float(D(item["targetAmount"])),
        "savedAmount": float(D(item["savedAmount"])),
        "deadline": item.get("deadline"),
    }


def _public_transaction(item: dict) -> dict:
    return {
        "id": item["id"],
        "date": item["date"],
        "amount": float(D(item["amount"])),
        "category": item["category"],
        "merchant": item["merchant"],
        "isRecurring": bool(item["isRecurring"]),
    }


def balance_of(state: dict) -> Decimal | None:
    if state["balance"] is None:
        return None
    return D(state["balance"])
