"""SQLite: сессии входа и данные пользователя одним JSON-документом (UserState).

Деньги в JSON хранятся строками Decimal — точность не теряется.
Соединение открывается на запрос (см. app.api.deps.get_store).
"""

import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from app.models import UserState

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    mode TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS states (
    user_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

SessionMode = Literal["demo", "telegram"]


@dataclass(frozen=True)
class Session:
    token: str
    user_id: str
    display_name: str
    mode: SessionMode


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(SCHEMA)
    return connection


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._db = connection

    def create_session(self, user_id: str, display_name: str, mode: SessionMode) -> Session:
        session = Session(secrets.token_urlsafe(32), user_id, display_name, mode)
        self._db.execute(
            "INSERT INTO sessions (token, user_id, display_name, mode, created_at) VALUES (?, ?, ?, ?, ?)",
            (session.token, user_id, display_name, mode, _now()),
        )
        self._db.commit()
        return session

    def session(self, token: str) -> Session | None:
        row = self._db.execute(
            "SELECT token, user_id, display_name, mode FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if row is None:
            return None
        return Session(row["token"], row["user_id"], row["display_name"], row["mode"])

    def load(self, user_id: str) -> UserState:
        row = self._db.execute("SELECT data FROM states WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return UserState()
        return UserState.model_validate_json(row["data"])

    def save(self, user_id: str, state: UserState) -> None:
        self._db.execute(
            """
            INSERT INTO states (user_id, data, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at
            """,
            (user_id, state.model_dump_json(), _now()),
        )
        self._db.commit()

    def clear(self, user_id: str) -> None:
        self.save(user_id, UserState())
