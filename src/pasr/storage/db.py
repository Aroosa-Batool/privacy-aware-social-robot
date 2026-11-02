from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

DB_FILENAME = "pasr.db"

MIGRATIONS: list[str] = [
    files("pasr.storage").joinpath(name).read_text(encoding="utf-8")
    for name in ("schema.sql", "feedback.sql")
]
"""Append new migrations; never edit applied ones. ``PRAGMA user_version`` records progress."""


def to_db(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return moment.astimezone(UTC).isoformat()


def from_db(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone()


def maybe_from_db(value: str | None) -> datetime | None:
    return None if value is None else from_db(value)


class Database:
    """Short-lived connections per operation, so the runtime thread, the dashboard and the CLI
    can all use the same file safely (WAL mode)."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def in_dir(cls, data_dir: Path) -> Database:
        return cls(data_dir / DB_FILENAME)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA secure_delete = ON")  # overwrite deleted biometric data on disk
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def migrate(self) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            with self.connect() as conn:
                conn.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
        return len(MIGRATIONS)

    def checkpoint(self) -> None:
        """Flush the WAL so deleted rows do not linger in the write-ahead log."""
        with self.connect() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
